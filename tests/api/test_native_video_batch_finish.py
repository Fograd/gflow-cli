"""Every acknowledged clip is independently polled/downloaded; no retry."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports.native_video_batch_driver import finish_batch
from gflow_cli.errors import NativeUIVideoBatchUnknownError
from tests.api.test_native_video_batch_codec import P, S, W, row

PAIRS = tuple(zip(S, W, strict=True))


@pytest.mark.asyncio
async def test_downloads_each_actual_clip_in_requested_order(monkeypatch, tmp_path):
    records = []
    for media, workflow in PAIRS:
        value = row(media, workflow)
        value[5][8] = [3]
        value[7][0] = [None] * 9
        value[7][0][8] = "https://flow-content.google/video/synthetic"
        records.append(value)
    rpc = AsyncMock(side_effect=records)

    def lookup(payload, **kw):
        return SimpleNamespace(media_id=kw["media_id"])

    download = AsyncMock(
        side_effect=[
            SimpleNamespace(path=tmp_path / "one.mp4"),
            SimpleNamespace(path=tmp_path / "two.mp4"),
        ]
    )
    monkeypatch.setattr("gflow_cli.api.transports.native_video_batch_driver.native_rpc", rpc)
    monkeypatch.setattr("gflow_cli.api.transports.native_video_batch_driver.existing_asset", lookup)
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.download_asset", download
    )
    started = []
    result = await finish_batch(
        object(),
        PAIRS,
        project=P,
        out_dir=tmp_path,
        deadline=time.monotonic() + 5,
        download=True,
        on_started=lambda value: started.append(value.media_id),
    )
    assert [video.status.media_id for video in result.videos] == list(S)
    assert [video.local_path for video in result.videos] == [
        tmp_path / "one.mp4",
        tmp_path / "two.mp4",
    ]
    assert started == list(S) and result.succeeded and download.await_count == 2


@pytest.mark.asyncio
async def test_download_failure_retains_all_actual_pairs_without_submit(monkeypatch, tmp_path):
    records = []
    for media, workflow in PAIRS:
        value = row(media, workflow)
        value[5][8] = [3]
        value[7][0] = [None] * 9
        value[7][0][8] = "https://flow-content.google/video/synthetic"
        records.append(value)
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.native_rpc",
        AsyncMock(side_effect=records),
    )
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.existing_asset",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.download_asset",
        AsyncMock(side_effect=OSError("private")),
    )
    with pytest.raises(NativeUIVideoBatchUnknownError) as exc:
        await finish_batch(
            object(),
            PAIRS,
            project=P,
            out_dir=tmp_path,
            deadline=time.monotonic() + 5,
            download=True,
            on_started=None,
        )
    assert exc.value.media_ids == S and exc.value.workflow_ids == W
    assert exc.value.phase == "video_poll" and "private" not in str(exc.value)


@pytest.mark.asyncio
async def test_wrong_project_poll_never_downloads(monkeypatch, tmp_path):
    value = row(S[0], W[0])
    value[1] = W[1]
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.native_rpc",
        AsyncMock(return_value=value),
    )
    download = AsyncMock()
    monkeypatch.setattr(
        "gflow_cli.api.transports.native_video_batch_driver.download_asset", download
    )
    with pytest.raises(NativeUIVideoBatchUnknownError):
        await finish_batch(
            object(),
            PAIRS,
            project=P,
            out_dir=tmp_path,
            deadline=time.monotonic() + 5,
            download=True,
            on_started=None,
        )
    download.assert_not_awaited()
