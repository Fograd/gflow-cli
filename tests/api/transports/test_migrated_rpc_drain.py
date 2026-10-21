"""Navigation-owned RPC drain and catalog acceptance contracts; no provider I/O."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.transports import migrated_resources
from gflow_cli.api.transports import migrated_upload_drain as source

P = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
async def test_catalog_init_registration_precedes_navigation_and_is_removed():
    page = MagicMock()
    session = AsyncMock()
    session.send.side_effect = [None, {"identifier": "owned-script"}, None]
    page.context.new_cdp_session = AsyncMock(return_value=session)
    page.evaluate = AsyncMock(return_value={"matches": 1, "complete": True, "bytes": 1048577})
    drain = source.UploadResponseDrain(page, P, rpc="Zzl0ze")
    await drain.install(navigation=True)
    assert drain.installed is True
    assert session.send.call_args_list[0].args == ("Page.enable",)
    method, params = session.send.call_args_list[1].args
    assert method == "Page.addScriptToEvaluateOnNewDocument"
    assert "Date.now()" in params["source"]
    assert "window.top" in params["source"]
    assert P in params["source"]
    assert "Zzl0ze" in params["source"]
    assert "worldName" not in params
    observation = await drain.result()
    assert observation.allows_ack is True
    assert observation.limit == source.MAX_PROJECT_RESPONSE_BYTES
    await drain.close()
    assert session.send.call_args_list[2].args == (
        "Page.removeScriptToEvaluateOnNewDocument",
        {"identifier": "owned-script"},
    )
    session.detach.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_page_cleanup_still_removes_owned_init_registration():
    page = MagicMock()
    session = AsyncMock()
    session.send.side_effect = [None, {"identifier": "owned-script"}, None]
    page.context.new_cdp_session = AsyncMock(return_value=session)
    drain = source.UploadResponseDrain(page, P, rpc="Zzl0ze")
    await drain.install(navigation=True)
    page.evaluate = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await drain.close()
    assert session.send.call_args_list[2].args[0] == "Page.removeScriptToEvaluateOnNewDocument"
    session.detach.assert_awaited_once()


@pytest.mark.parametrize("rpc", ["unrelated", "maseQ,Zzl0ze", "", "pGCYOe"])
def test_only_internal_measured_response_readers_are_supported(rpc):
    with pytest.raises(ValueError):
        source.UploadResponseDrain(MagicMock(), P, rpc=rpc)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "complete,size,matches", [(False, 11, 1), (False, 2097153, 1), (True, 11, 2)]
)
async def test_catalog_observed_bad_drain_rejects_valid_canonical_payload(
    monkeypatch, complete, size, matches
):
    page = MagicMock()
    handlers = {}
    page.on.side_effect = lambda name, handler: handlers.update({name: handler})
    canonical = MagicMock(
        url=(
            "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute"
            "?rpcids=Zzl0ze&source-path=%2Fproject%2F" + P
        ),
        status=200,
        headers={},
    )
    canonical.text = AsyncMock(return_value="canonical-only")
    monkeypatch.setattr(
        migrated_resources, "parse_frames", lambda text: [("Zzl0ze", [None, None, []])]
    )
    monkeypatch.setattr(migrated_resources, "project_media", lambda payload, project: [])
    monkeypatch.setattr(source.UploadResponseDrain, "install", AsyncMock())
    close = AsyncMock()
    monkeypatch.setattr(source.UploadResponseDrain, "close", close)
    monkeypatch.setattr(
        source.UploadResponseDrain,
        "result",
        AsyncMock(return_value=source.DrainObservation(True, complete, size, matches, 2097152)),
    )

    async def goto(url):
        await handlers["response"](canonical)

    page.goto = AsyncMock(side_effect=goto)
    with pytest.raises(ValueError, match="stream"):
        await migrated_resources.read_project_payload(page, P)
    assert canonical.text.await_count == 1
    page.goto.assert_awaited_once()
    page.remove_listener.assert_called_once()
    close.assert_awaited_once()
