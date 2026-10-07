"""Extension callers must validate fresh output identity and actual MP4 bytes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from gflow_cli.api import native_extension
from gflow_cli.api.transports import native_asset_download
from gflow_cli.api.transports.native_asset_lookup import NativeAsset
from gflow_cli.mcp import tools
from gflow_cli.selfhost import extension_worker

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
@pytest.mark.parametrize("interface", ["worker", "mcp"])
@pytest.mark.parametrize("failure", ["html", "wrong-workflow", "external-url"])
async def test_extension_refuses_unverified_download(tmp_path, monkeypatch, interface, failure):
    started = native_extension.new_extension_started(P, M, 1)
    record = SimpleNamespace(
        project_id=P,
        media_id=started.media_ids[0],
        workflow_id=started.workflow_ids[0],
        video_url="https://flow-content.google/video/expired?Signature=old",
    )
    asset = NativeAsset(
        record.media_id,
        P,
        M if failure == "wrong-workflow" else record.workflow_id,
        "video",
        "http://localhost/private"
        if failure == "external-url"
        else "https://flow-content.google/video/fresh?Signature=private",
        1280,
        720,
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    async def submit(*args, **kwargs):
        await kwargs["on_started"](started)
        return started

    client.extend_native_video = AsyncMock(side_effect=submit)
    client.wait_native_extension = AsyncMock(return_value=[record])
    client.get_native_asset = AsyncMock(return_value=asset)

    async def unsafe_download(_url, path):
        path.write_bytes(b"<html>expired or unrelated</html>")

    client.download = AsyncMock(side_effect=unsafe_download)
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"<html>no</html>"
        )

    http_client = httpx.AsyncClient
    monkeypatch.setattr(
        native_asset_download.httpx,
        "AsyncClient",
        lambda **kwargs: http_client(transport=httpx.MockTransport(response), **kwargs),
    )
    if interface == "worker":
        monkeypatch.setattr(extension_worker, "FlowApiClient", lambda **_: client)
        monkeypatch.setattr(extension_worker, "extend_native_video", client.extend_native_video)
        monkeypatch.setattr(extension_worker, "wait_native_extension", client.wait_native_extension)
        with pytest.raises(native_extension.NativeExtensionUnknownError) as caught:
            await extension_worker._run_extension(
                "fixture", P, {"mediaGenerationId": M, "prompt": "Continue"}, tmp_path
            )
        error = caught.value.to_problem_details()
        assert caught.value.retryable is False
    else:
        monkeypatch.setattr(tools, "FlowApiClient", lambda **_: client)
        monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
        monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
        result = await tools.gflow_extend_native_video(P, M, "Continue", out_dir=str(tmp_path))
        assert "error" in result, "Unvalidated bytes were reported as a successful MP4"
        error = result["error"]
    assert error["outcome_unknown"] is True
    assert error.get("retryable", False) is False
    assert error["media_ids"] == list(started.media_ids)
    assert error["workflow_ids"] == list(started.workflow_ids)
    assert not list(tmp_path.glob("*.mp4"))
    assert "Signature" not in str(error) and "localhost" not in str(error)
    client.extend_native_video.assert_awaited_once()
    client.download.assert_not_awaited()
    assert len(requests) == (1 if failure == "html" else 0)
    assert len(list(tmp_path.glob("*started*.json"))) == 1
