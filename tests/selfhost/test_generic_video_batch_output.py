"""Private N-output projection preserves every exact clip and scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.selfhost.store import Store
from gflow_cli.selfhost.video_batch_output import publish_video_batch

P = "11111111-1111-4111-8111-111111111111"
M = ["22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"]
W = ["44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555"]


def output(tmp_path):
    videos = []
    for media, workflow in zip(M, W, strict=True):
        path = tmp_path / (media + ".mp4")
        path.write_bytes(b"\x00\x00\x00\x18ftypisomsynthetic")
        videos.append(
            dict(
                media_id=media,
                workflow_id=workflow,
                project_id=P,
                succeeded=True,
                local_path=str(path),
            )
        )
    return dict(project_id=P, returned_count=2, status="ok", videos=videos)


@pytest.mark.asyncio
async def test_all_clips_are_cached_same_scope_and_returned(monkeypatch, tmp_path):
    store = Store(tmp_path)
    raw = output(tmp_path)
    monkeypatch.setattr(
        "gflow_cli.selfhost.video_batch_output.probe",
        AsyncMock(return_value=SimpleNamespace(width=1280, height=720, duration=8)),
    )
    result = await publish_video_batch(store, raw, profile="pro1", project=P, out=tmp_path, count=2)
    assert [item["mediaGenerationId"] for item in result["media"]] == M
    assert result["completedCount"] == 2 and result["requestedCount"] == 2
    assert all(store.asset_get(media)["profile"] == "pro1" for media in M)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["duplicate", "foreign", "escape", "count", "workflow"])
async def test_invalid_complete_envelope_never_caches_any_clip(monkeypatch, tmp_path, bad):
    store = Store(tmp_path)
    raw = output(tmp_path)
    if bad == "duplicate":
        raw["videos"][1]["media_id"] = M[0]
    if bad == "foreign":
        raw["videos"][1]["project_id"] = W[0]
    if bad == "escape":
        raw["videos"][1]["local_path"] = "/tmp/not-contained.mp4"
    if bad == "count":
        raw["returned_count"] = 1
    if bad == "workflow":
        raw["videos"][1]["workflow_id"] = W[0]
    monkeypatch.setattr(
        "gflow_cli.selfhost.video_batch_output.probe",
        AsyncMock(return_value=SimpleNamespace(width=1280, height=720, duration=8)),
    )
    with pytest.raises(ValueError):
        await publish_video_batch(store, raw, profile="pro1", project=P, out=tmp_path, count=2)
    for media in M:
        with pytest.raises(KeyError):
            store.asset_get(media)
