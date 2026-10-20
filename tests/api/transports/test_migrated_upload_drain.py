"""Scoped stream-drain contract: no extra request, ACK bytes remain canonical."""

import json
import shutil
import subprocess
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import migrated_upload_drain as source

PROJECT = "22222222-2222-4222-8222-222222222222"
URL = (
    "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute"
    "?rpcids=maseQ&source-path=%2Fproject%2F" + PROJECT
)


def run_js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the browser-native stream contract")
    script = (
        "global.window=global; global.location={href:'https://flow.google.com/'};"
        "(async()=>{const install=" + source.INSTALL_SCRIPT + ";"
        "const control=" + source.CONTROL_SCRIPT + ";"
        "const args="
        + json.dumps({"key": "unit-drain", "project": PROJECT, "limit": 256, "timeoutMs": 1000})
        + ";"
        "const url="
        + json.dumps(URL)
        + ";"
        + body
        + "})().catch(e=>{console.error(e);process.exit(1)});"
    )
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, timeout=5, check=True
    )
    return json.loads(result.stdout)


def test_original_promise_response_receiver_and_arguments_preserved():
    result = run_js("""
      const response=new Response('{"ok":true}'); Object.defineProperty(response,'url',{value:url});
      const promise=Promise.resolve(response), receiver={tag:1}, init={method:'POST',body:'secret'};
      let calls=0, sameArgs=false, sameThis=false;
      const original=window.fetch=function(...args){
        calls++;sameArgs=args[0]===url&&args[1]===init;
        sameThis=this===receiver;return promise};
      install(args);
      const returned=window.fetch.call(receiver,url,init);
      const samePromise=returned===promise, sameResponse=(await returned)===response;
      const application=await response.text();
      const observation=await control({key:args.key,action:'result'});
      await control({key:args.key,action:'close'});
      console.log(JSON.stringify({calls,sameArgs,sameThis,samePromise,sameResponse,application,observation,restored:window.fetch===original}));
    """)
    assert result == {
        "calls": 1,
        "sameArgs": True,
        "sameThis": True,
        "samePromise": True,
        "sameResponse": True,
        "application": '{"ok":true}',
        "observation": {"matches": 1, "complete": True, "bytes": 11},
        "restored": True,
    }


@pytest.mark.parametrize(
    "change",
    [
        "url.replace('https:', 'http:')",
        "url.replace('flow.google.com', 'foreign.example')",
        "url.replace('maseQ', 'ogiZ0b')",
        "url+'&rpcids=maseQ'",
        "url+'&source-path=%2Fproject%2F'+args.project",
        "url.replace(args.project,'33333333-3333-4333-8333-333333333333')",
        "url.replace('batchexecute','unrelated')",
    ],
)
def test_other_routes_are_untouched(change):
    result = run_js(
        """
      let clones=0,calls=0;
      const original=window.fetch=function(){calls++;return Promise.resolve({
        status:200,url,redirected:false,clone(){clones++;throw new Error('SECRET')}})};
      install(args);
      await window.fetch("""
        + change
        + """,{method:'POST'});
      const observation=await control({key:args.key,action:'result'});
      await control({key:args.key,action:'close'});
      console.log(JSON.stringify({calls,clones,observation,restored:window.fetch===original}));
    """
    )
    assert result["calls"] == 1
    assert result["clones"] == 0
    assert result["observation"] == {"matches": 0, "complete": False, "bytes": 0}
    assert result["restored"] is True


@pytest.mark.parametrize("kind", ["oversize", "broken", "redirected", "duplicate"])
def test_observed_bad_stream_cannot_claim_clean_completion(kind):
    result = run_js(
        """
      const kind="""
        + json.dumps(kind)
        + """;
      window.fetch=()=>{const stream=new ReadableStream({start(c){
        c.enqueue(new Uint8Array(kind==='oversize'?257:11));
        if(kind==='broken')c.error(new Error('SECRET'));else c.close()}});
        const response=new Response(stream);Object.defineProperty(response,'url',{value:url});
        if(kind==='redirected')Object.defineProperty(response,'redirected',{value:true});
        return Promise.resolve(response)};
      install(args);
      const response=await window.fetch(url,{method:'POST'});
      if(kind==='duplicate')await window.fetch(url,{method:'POST'});
      try{await response.arrayBuffer()}catch{}
      const observation=await control({key:args.key,action:'result'});
      await control({key:args.key,action:'close'});
      console.log(JSON.stringify(observation));
    """
    )
    assert result["matches"] >= 1
    assert result["complete"] is False
    assert "SECRET" not in json.dumps(result)


def test_cleanup_never_overwrites_later_wrapper_and_old_wrapper_is_inactive():
    result = run_js("""
      let clones=0;
      window.fetch=()=>Promise.resolve({status:200,url,redirected:false,
        clone(){clones++;throw Error('SECRET')}});
      install(args);
      const ours=window.fetch;
      const newer=window.fetch=function(...a){return Reflect.apply(ours,this,a)};
      await control({key:args.key,action:'close'});
      await window.fetch(url,{method:'POST'});
      console.log(JSON.stringify({newerPreserved:window.fetch===newer,clones,removed:window[args.key]===undefined}));
    """)
    assert result == {"newerPreserved": True, "clones": 0, "removed": True}


@pytest.mark.asyncio
async def test_install_failure_preserves_canonical_path():
    page = AsyncMock()
    page.evaluate.side_effect = RuntimeError("SECRET")
    drain = source.UploadResponseDrain(page, PROJECT)
    await drain.install()
    observation = await drain.result()
    await drain.close()
    assert observation.allows_ack is True
    assert observation.observed is False
    assert page.evaluate.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        {"matches": 1, "complete": False, "bytes": 257},
        {"matches": 2, "complete": True, "bytes": 11},
        {"matches": 1, "complete": True, "bytes": 1048577},
        {"matches": 1, "complete": True, "bytes": True},
        {"matches": 1, "complete": True, "bytes": 0},
        {"matches": 0, "complete": True, "bytes": 11},
        None,
    ],
)
async def test_observed_or_unreadable_result_fails_closed(raw):
    page = AsyncMock()
    page.evaluate.side_effect = [True, raw, None]
    drain = source.UploadResponseDrain(page, PROJECT)
    await drain.install()
    observation = await drain.result()
    await drain.close()
    assert observation.allows_ack is False


def test_rejected_original_fetch_keeps_exact_promise_and_error_without_cloning():
    result = run_js("""
      const failure = new Error('SECRET');
      const promise = Promise.reject(failure);
      window.fetch = () => promise;
      install(args);
      const returned = window.fetch(url, {method:'POST'});
      let sameError = false;
      try { await returned; } catch (error) { sameError = error === failure; }
      const observation = await control({key:args.key, action:'result'});
      await control({key:args.key, action:'close'});
      console.log(JSON.stringify({samePromise:returned===promise, sameError, observation}));
    """)
    assert result == {
        "samePromise": True,
        "sameError": True,
        "observation": {"matches": 1, "complete": False, "bytes": 0},
    }


def test_nonsettling_clone_expires_without_awaiting_cancellation():
    result = run_js("""
      args.timeoutMs = 10;
      let cancelled = false;
      const response = {status:200, url, redirected:false, clone(){return {body:{getReader(){
        return {read:()=>new Promise(()=>{}), cancel(){cancelled=true;return new Promise(()=>{})},
                releaseLock(){}};
      }}}}};
      const promise = Promise.resolve(response);
      const original = window.fetch = () => promise;
      install(args);
      const returned = window.fetch(url, {method:'POST'});
      const observation = await control({key:args.key, action:'result'});
      await control({key:args.key, action:'close'});
      console.log(JSON.stringify({samePromise:returned===promise, cancelled,
          restored:window.fetch===original, observation}));
    """)
    assert result == {
        "samePromise": True,
        "cancelled": True,
        "restored": True,
        "observation": {"matches": 1, "complete": False, "bytes": 0},
    }


def test_observer_registration_failure_does_not_change_original_return():
    result = run_js("""
      const promise = {then(){throw Error('SECRET')}};
      window.fetch = () => promise;
      install(args);
      const returned = window.fetch(url, {method:'POST'});
      const observation = await control({key:args.key, action:'result'});
      await control({key:args.key, action:'close'});
      console.log(JSON.stringify({samePromise:returned===promise, observation}));
    """)
    assert result == {
        "samePromise": True,
        "observation": {"matches": 1, "complete": False, "bytes": 0},
    }


@pytest.mark.parametrize("rpc", ["Zzl0ze", "ogiZ0b"])
def test_measured_rpc_parameter_is_exact_and_leaves_other_rpc_untouched(rpc):
    result = run_js(
        """
      args.rpc = """
        + json.dumps(rpc)
        + """;
      const scoped = url.replace('maseQ', args.rpc);
      let clones = 0, calls = 0;
      window.fetch = function(target) {
        calls++;
        const response = new Response('{"ok":true}');
        Object.defineProperty(response, 'url', {value:target});
        const clone = response.clone.bind(response);
        response.clone = () => {clones++;return clone()};
        return Promise.resolve(response);
      };
      install(args);
      const unrelated = await window.fetch(url, {method:'POST'});
      await unrelated.text();
      const response = await window.fetch(scoped, {method:'POST'});
      await response.text();
      const observation = await control({key:args.key, action:'result'});
      await control({key:args.key, action:'close'});
      console.log(JSON.stringify({clones, calls, observation}));
    """
    )
    assert result == {
        "clones": 1,
        "calls": 2,
        "observation": {"matches": 1, "complete": True, "bytes": 11},
    }
