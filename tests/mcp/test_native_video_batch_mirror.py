"""Actual direct MCP queue->worker->asset path returns every clip."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gflow_cli.api.video import VideoBatchResult, VideoResult, VideoStatus
from gflow_cli.mcp.tools import _run_generation_task
from tests.mcp.test_tools_wired import _FakeFlowApiClient
from tests.mcp.test_tools_wired import temp_db as _temp_db
from tests.selfhost.test_generic_video_batch_output import M, P, W

temp_db = _temp_db


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_direct_mcp_returns_all_batch_ids_and_files(temp_db, tmp_path, partial):
    results = []
    for media, workflow in zip(M, W, strict=True):
        path = tmp_path / (media + ".mp4")
        path.write_bytes(b"synthetic")
        results.append(
            VideoResult(
                VideoStatus(
                    media_id=media,
                    status=(
                        "MEDIA_GENERATION_STATUS_FAILED"
                        if partial and media == M[1]
                        else "MEDIA_GENERATION_STATUS_SUCCESSFUL"
                    ),
                ),
                (None if partial and media == M[1] else path),
                P,
                workflow,
                workflow,
            )
        )
    fake = _FakeFlowApiClient()
    fake.generate_videos_batch = AsyncMock(return_value=VideoBatchResult(tuple(results), P))
    with (
        patch("gflow_cli.worker.daemon.FlowApiClient", return_value=fake),
        patch(
            "gflow_cli.mcp.tools.get_settings",
            return_value=MagicMock(
                resolved_db_path=lambda: temp_db.path,
                profile_subdir=lambda _: tmp_path / "profile",
                timeout_seconds=30,
            ),
        ),
        patch(
            "gflow_cli.worker.daemon.get_settings",
            return_value=MagicMock(
                profile_subdir=lambda _: tmp_path / "profile",
                headless=True,
                transport=None,
                output_dir=tmp_path,
            ),
        ),
    ):
        result = await _run_generation_task(
            profile="default",
            task_type="t2v",
            payload={"prompt": "synthetic", "project_id": P, "count": 2, "aspect": "16:9"},
        )
    assert result["status"] == ("failed" if partial else "completed")
    assert result["flow_media_ids"] == M and result["flow_workflow_ids"] == W
    assert set(result["files"]) == {
        str(tmp_path / (media + ".mp4")) for media in (M[:1] if partial else M)
    }
    fake.generate_video.assert_not_awaited()
