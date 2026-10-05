"""Fresh owned-video cache measurements when Google omits dimensions."""

from unittest.mock import AsyncMock

import pytest

from gflow_cli.selfhost.concatenate import VideoInfo
from gflow_cli.selfhost.native_video_cache import _verified_file


@pytest.mark.asyncio
async def test_missing_both_dimensions_uses_decoded_owned_bytes(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    measured = AsyncMock(return_value=VideoInfo(8, 1280, 720, True))
    monkeypatch.setattr("gflow_cli.selfhost.native_video_cache.probe", measured)
    await _verified_file(path, {"width": None, "height": None})
    measured.assert_awaited_once_with(path, timeout_s=15)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dimensions",
    [
        {"width": 1280, "height": None},
        {"width": True, "height": 720},
        {"width": 640, "height": 480},
    ],
)
async def test_supplied_dimensions_must_be_complete_and_match(tmp_path, monkeypatch, dimensions):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    monkeypatch.setattr(
        "gflow_cli.selfhost.native_video_cache.probe",
        AsyncMock(return_value=VideoInfo(8, 1280, 720, True)),
    )
    with pytest.raises(ValueError):
        await _verified_file(path, dimensions)


@pytest.mark.asyncio
async def test_measured_dimensions_must_be_positive(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    monkeypatch.setattr(
        "gflow_cli.selfhost.native_video_cache.probe",
        AsyncMock(return_value=VideoInfo(8, 0, 720, True)),
    )
    with pytest.raises(ValueError):
        await _verified_file(path, {"width": None, "height": None})
