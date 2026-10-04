"""CLI count-N emits/relocates/records every output instead of the first."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.video import GenerateVideoRequest, VideoBatchResult, VideoResult, VideoStatus
from gflow_cli.cli_video import _generate_and_report
from tests.selfhost.test_generic_video_batch_output import M, P, W


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [False, True])
async def test_count_two_uses_batch_and_emits_both_relocated_files(tmp_path, monkeypatch, provider):
    request = GenerateVideoRequest(prompt="synthetic", count=2)
    results = []
    for media, workflow in zip(M, W, strict=True):
        path = tmp_path / (media + ".mp4")
        path.write_bytes(b"clip")
        results.append(
            VideoResult(
                VideoStatus(media_id=media, status="MEDIA_GENERATION_STATUS_SUCCESSFUL"),
                path,
                P,
                workflow,
                workflow,
            )
        )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    client.generate_videos_batch = AsyncMock(return_value=VideoBatchResult(tuple(results), P))
    client.generate_video = AsyncMock(side_effect=AssertionError("singular path"))
    recorder = MagicMock()
    monkeypatch.setattr("gflow_cli.cli_video.FlowApiClient", lambda **kw: client)
    monkeypatch.setattr("gflow_cli.cli_video.OperationRecorder.open", lambda settings: recorder)
    monkeypatch.setattr(
        "gflow_cli.services.mentions.resolve_and_apply", AsyncMock(return_value=request)
    )
    monkeypatch.setattr("gflow_cli.cli_image.wire_refresh_resolver", lambda *a, **kw: None)
    monkeypatch.setattr("gflow_cli.cli_video.cloud_info_from_path", lambda path: None)
    policy = AsyncMock(return_value=VideoBatchResult(tuple(results), P))
    monkeypatch.setattr("gflow_cli.services.video_captcha.generate_video_with_captcha", policy)
    output = []
    monkeypatch.setattr("gflow_cli.cli_video.json_output.emit", output.append)
    await _generate_and_report(
        request,
        profile_name="pro1",
        profile_dir=tmp_path,
        out_dir=tmp_path,
        output_file=tmp_path / "output.mp4",
        as_json=True,
        project_id=P,
        captcha_controls={"captchaRetry": 2} if provider else None,
    )
    assert [v["media_id"] for v in output[0]["videos"]] == M
    assert [v["local_path"] for v in output[0]["videos"]] == [
        str(tmp_path / "output_1.mp4"),
        str(tmp_path / "output_2.mp4"),
    ]
    assert recorder.record_completed_video.call_count == 2
    client.generate_video.assert_not_awaited()

    if provider:
        policy.assert_awaited_once()
        assert policy.await_args.kwargs["req"].count == 2
        client.generate_videos_batch.assert_not_awaited()
