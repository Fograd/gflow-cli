"""Real durable queue path records all N SDK outputs and recovery handles."""

from unittest.mock import AsyncMock, patch

import pytest

from gflow_cli.api.video import VideoBatchResult, VideoResult, VideoStatus
from gflow_cli.worker.daemon import FlowWorker
from gflow_cli.worker.queue import QueueRepository
from tests.selfhost.test_generic_video_batch_output import M, P, W
from tests.worker.test_daemon import FakeFlowApiClient
from tests.worker.test_daemon import temp_db as _temp_db

temp_db = _temp_db


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [False, True])
async def test_durable_worker_batch_keeps_all_completed_outputs(temp_db, tmp_path, provider):
    repo = QueueRepository(temp_db)
    task = repo.enqueue_task(
        task_id="batch-native-test",
        profile_name="default",
        task_type="t2v",
        payload={
            "prompt": "synthetic",
            "aspect": "16:9",
            "project_id": P,
            "count": 2,
            **({"captchaRetry": 2} if provider else {}),
            "out_dir": str(tmp_path),
        },
    )
    videos = []
    for media, workflow in zip(M, W, strict=True):
        path = tmp_path / (media + ".mp4")
        path.write_bytes(b"synthetic")
        videos.append(
            VideoResult(
                VideoStatus(media_id=media, status="MEDIA_GENERATION_STATUS_SUCCESSFUL"),
                path,
                P,
                workflow,
                workflow,
            )
        )
    fake = FakeFlowApiClient()
    fake.generate_videos_batch = AsyncMock(return_value=VideoBatchResult(tuple(videos), P))
    policy = AsyncMock(return_value=VideoBatchResult(tuple(videos), P))
    worker = FlowWorker("default", str(temp_db.path))
    try:
        with (
            patch("gflow_cli.worker.daemon.FlowApiClient", return_value=fake),
            patch("gflow_cli.services.video_captcha.generate_video_with_captcha", policy),
        ):
            await worker.process_task(task)
        result = repo.get_task(task.task_id)
        assert result.status == "completed"
        assert result.checkpoint["media_ids"] == M and result.checkpoint["workflow_ids"] == W
        if provider:
            policy.assert_awaited_once()
            assert policy.await_args.kwargs["req"].count == 2
            fake.generate_videos_batch.assert_not_awaited()
        else:
            fake.generate_videos_batch.assert_awaited_once()
        fake.generate_video.assert_not_awaited()
    finally:
        worker.close()
