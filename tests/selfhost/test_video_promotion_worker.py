"""Native promotion completion verifies dimensions before exposing downloaded output."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.native_video_upscale import NativeVideoUpscaleUnknownError, new_promotion_started
from gflow_cli.selfhost import video_promotion_worker as module

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
@pytest.mark.parametrize("height", [360, 720])
async def test_completion_checks_target_and_no_protected_url(monkeypatch, tmp_path, height):
    started = new_promotion_started(P, M, W, "720p")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_native_asset(self, project, media):
            assert (project, media) == (P, started.media_ids[0])
            return SimpleNamespace(
                kind="video", workflow_id=W, width=1280, height=height, url="secret-signed-url"
            )

    monkeypatch.setattr(module, "FlowApiClient", lambda **kwargs: Client())
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(profile_subdir=lambda profile: tmp_path)
    )

    async def submit(client, **kwargs):
        assert kwargs["resolution"] == "720p" and kwargs["model_key"] == "specific"
        await kwargs["on_started"](started)
        return started

    monkeypatch.setattr(module, "upscale_native_video", submit)
    monkeypatch.setattr(module, "wait_native_promotion", AsyncMock(return_value=()))
    download = AsyncMock(return_value=SimpleNamespace(path=tmp_path / "result.mp4"))
    monkeypatch.setattr(module, "download_asset", download)
    if height == 360:
        with pytest.raises(NativeVideoUpscaleUnknownError):
            await module.run_promotion(
                "pro1",
                P,
                {"mediaGenerationId": M, "resolution": "720p", "modelKey": "specific"},
                tmp_path,
            )
        download.assert_not_awaited()
    else:
        result = await module.run_promotion(
            "pro1",
            P,
            {"mediaGenerationId": M, "resolution": "720p", "modelKey": "specific"},
            tmp_path,
        )
        assert result["results"][0]["height"] == 720 and "secret" not in str(result)
        assert (tmp_path / "promotion-started.json").is_file()
