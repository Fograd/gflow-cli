"""Private batch worker consumes one SDK call and retains every actual handle."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.video import VideoBatchResult, VideoResult, VideoStarted, VideoStatus
from gflow_cli.errors import NativeUIVideoBatchUnknownError
from gflow_cli.selfhost.general_video_worker import generate_payload
from tests.selfhost.test_generic_video_batch_output import M, P, W


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_single_batch_call_preserves_all_ids(monkeypatch, tmp_path, unknown):
    output = []
    results = tuple(
        VideoResult(
            VideoStatus(media_id=media, status="MEDIA_GENERATION_STATUS_SUCCESSFUL"),
            tmp_path / (media + ".mp4"),
            P,
            workflow,
            workflow,
        )
        for media, workflow in zip(M, W, strict=True)
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_videos_batch(self, **kwargs):
            for value in results:
                await kwargs["on_started"](
                    VideoStarted(
                        media_id=value.status.media_id, project_id=P, workflow_id=value.workflow_id
                    )
                )
            if unknown:
                raise NativeUIVideoBatchUnknownError(
                    project_id=P, media_ids=tuple(M), workflow_ids=tuple(W), phase="video_poll"
                )
            return VideoBatchResult(results, P)

        generate_video = AsyncMock(side_effect=AssertionError("Singular call is not permitted"))

    client = Client()
    monkeypatch.setattr(
        "gflow_cli.selfhost.general_video_worker.FlowApiClient", lambda **kw: client
    )
    monkeypatch.setattr(
        "gflow_cli.selfhost.general_video_worker._make_provider_dir", lambda profile: tmp_path
    )
    monkeypatch.setattr(
        "gflow_cli.selfhost.general_video_worker.get_settings",
        lambda: SimpleNamespace(headless=True),
    )
    monkeypatch.setattr("gflow_cli.selfhost.general_video_worker.json_output.emit", output.append)
    payload = {"prompt": "synthetic", "count": 2, "aspectRatio": "16:9"}
    if unknown:
        with pytest.raises(SystemExit) as exc:
            await generate_payload("pro1", P, tmp_path, payload)
        assert exc.value.code == 40 and output[0]["error"]["media_ids"] == M
    else:
        await generate_payload("pro1", P, tmp_path, payload)
        assert (
            output[0]["returned_count"] == 2 and [v["media_id"] for v in output[0]["videos"]] == M
        )
    checkpoint = json.loads((tmp_path / "video-checkpoint.json").read_text())
    assert checkpoint["media_ids"] == M and checkpoint["workflow_ids"] == W
    client.generate_video.assert_not_awaited()
