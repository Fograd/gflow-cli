"""Exact video submit token overrides, without browser or paid calls."""

import json
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides, rewrite_submit
from gflow_cli.errors import WireFormatError

P = "00000000-0000-4000-8000-000000000001"
TOKEN = "replacement-token-value-abcdefghijklmnopqrstuvwxyz"


def body(rpc="YhhmEf", project=P, count=1):
    args = [
        [[None, "model", 123, ["prompt"]] for _ in range(count)],
        [
            None,
            22,
            None,
            None,
            None,
            project,
            None,
            None,
            None,
            None,
            ["original-token-abcdefghijklmnopqrstuvwxyz", 1],
        ],
        ["batch", 1],
    ]
    return urlencode(
        {"f.req": json.dumps([[[rpc, json.dumps(args), None, "generic"]]]), "at": "keep"}
    )


def decoded(value):
    return json.loads(json.loads(parse_qs(value)["f.req"][0])[0][0][1])


@pytest.mark.parametrize("rpc", ["YhhmEf", "eb1hJf", "nprQif", "MZZa6b"])
def test_only_token_changes(rpc):
    original = decoded(body(rpc))
    result = decoded(rewrite_submit(body(rpc), project=P, count=1, token=TOKEN))
    original[1][10][0] = TOKEN
    assert result == original
    assert parse_qs(rewrite_submit(body(rpc), project=P, count=1, token=TOKEN))["at"] == ["keep"]


@pytest.mark.parametrize(
    "value", [body(project="wrong"), body(count=2), body("ogiZ0b"), "f.req=[]", "f.req=x"]
)
def test_unknown_or_foreign_envelope_refuses(value):
    with pytest.raises(WireFormatError):
        rewrite_submit(value, project=P, count=1, token=TOKEN)


@pytest.mark.asyncio
async def test_consumes_override_once():
    calls = []

    async def token(page):
        calls.append(page)
        return TOKEN

    override = VideoOverrides(project=P, count=1, token=token)
    assert decoded(await override.apply(object(), body()))[1][10][0] == TOKEN
    with pytest.raises(WireFormatError):
        await override.apply(object(), body())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_bad_envelope_does_not_consume_token():
    calls = []

    async def token(page):
        calls.append(page)
        return TOKEN

    override = VideoOverrides(project=P, count=1, token=token)
    with pytest.raises(WireFormatError):
        await override.apply(object(), body(project="wrong"))
    assert calls == []


@pytest.mark.asyncio
async def test_unrelated_rpc_never_consumes_token():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_video_overrides import guard_video_submit

    token = AsyncMock(return_value=TOKEN)
    override = VideoOverrides(project=P, count=1, token=token)
    route = SimpleNamespace(fallback=AsyncMock(), continue_=AsyncMock())
    await guard_video_submit(
        route,
        SimpleNamespace(
            method="POST",
            post_data=body("jwpduf"),
            url="https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=jwpduf",
        ),
        object(),
        override,
    )
    route.fallback.assert_awaited_once()
    token.assert_not_awaited()
    assert not override.dispatched


@pytest.mark.asyncio
async def test_actual_dispatch_has_replaced_body_and_one_use():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_video_overrides import guard_video_submit

    override = VideoOverrides(project=P, count=1, token=AsyncMock(return_value=TOKEN))
    route = SimpleNamespace(fallback=AsyncMock(), continue_=AsyncMock())
    await guard_video_submit(
        route,
        SimpleNamespace(
            method="POST",
            post_data=body(),
            url="https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=YhhmEf",
        ),
        object(),
        override,
    )
    sent = route.continue_.await_args.kwargs["post_data"]
    assert decoded(sent)[1][10][0] == TOKEN
    assert override.dispatched


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,method",
    [
        ("https://example.test/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=YhhmEf", "POST"),
        ("https://flow.google.com/other/batchexecute?rpcids=YhhmEf", "POST"),
        (
            "http://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=YhhmEf",
            "POST",
        ),
        (
            "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=YhhmEf",
            "GET",
        ),
    ],
)
async def test_outgoing_endpoint_proof_before_consumption(url, method):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_video_overrides import guard_video_submit

    token = AsyncMock(return_value=TOKEN)
    override = VideoOverrides(project=P, count=1, token=token)
    route = SimpleNamespace(fallback=AsyncMock(), continue_=AsyncMock())
    with pytest.raises(WireFormatError):
        await guard_video_submit(
            route, SimpleNamespace(url=url, method=method, post_data=body()), object(), override
        )
    token.assert_not_awaited()
    assert not override.used


@pytest.mark.parametrize(
    "dispatched,project,expected",
    [
        (False, P, False),
        (True, "foreign", False),
        (True, None, False),
        (True, P, True),
    ],
)
def test_acknowledgement_scope(dispatched, project, expected):
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_video_overrides import acknowledgement_allowed

    override = VideoOverrides(project=P, count=1, token=AsyncMock())
    override.dispatched = dispatched
    assert acknowledgement_allowed(override, project) is expected


def test_boolean_credential_flag_refused():
    pairs = parse_qs(body())
    frames = json.loads(pairs["f.req"][0])
    args = json.loads(frames[0][0][1])
    args[1][10][1] = True
    frames[0][0][1] = json.dumps(args)
    value = urlencode({"f.req": json.dumps(frames)})
    with pytest.raises(WireFormatError):
        rewrite_submit(value, project=P, count=1, token=TOKEN)


@pytest.mark.asyncio
async def test_closed_inherited_attempt_refuses_late_token_result():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api.transports.migrated_video_overrides import guard_video_submit

    gate = asyncio.Event()

    async def token(page):
        await gate.wait()
        return TOKEN

    override = VideoOverrides(project=P, count=1, token=token)
    route = SimpleNamespace(continue_=AsyncMock(), fallback=AsyncMock())
    request = SimpleNamespace(
        url="https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute",
        method="POST",
        post_data=body(),
    )
    task = asyncio.create_task(guard_video_submit(route, request, object(), override))
    await asyncio.sleep(0)
    override.close()
    gate.set()
    with pytest.raises(WireFormatError, match="closed"):
        await task
    route.continue_.assert_not_awaited()
    assert not override.dispatched
