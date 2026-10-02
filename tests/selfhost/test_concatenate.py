"""Local concatenate contracts and real FFmpeg regression, no Google credits."""

from __future__ import annotations

import shutil
import subprocess
from array import array
from pathlib import Path

import pytest

from gflow_cli.selfhost.concatenate import Clip, VideoInfo, execute, validate


def info(duration: float = 2, width: int = 64, height: int = 64) -> VideoInfo:
    return VideoInfo(duration=duration, width=width, height=height, has_audio=True)


@pytest.mark.parametrize("count", [0, 1, 11])
def test_clip_count_bounds(count: int, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="2 to 10"):
        validate([Clip(tmp_path / f"{i}.mp4") for i in range(count)], [info()] * count)


@pytest.mark.parametrize("start,end", [(float("nan"), 0), (-1, 0), (11, 0), (1, 1)])
def test_trim_bounds(start: float, end: float, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="trim"):
        validate([Clip(tmp_path / "a.mp4", start, end), Clip(tmp_path / "b.mp4")], [info(), info()])


def test_dimensions_must_match(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        validate([Clip(tmp_path / "a.mp4"), Clip(tmp_path / "b.mp4")], [info(), info(width=128)])


def test_valid_trims(tmp_path: Path) -> None:
    validate(
        [Clip(tmp_path / "a.mp4", 0.2, 0.3), Clip(tmp_path / "b.mp4", 0.4, 0.5)], [info(), info()]
    )


@pytest.fixture
def real_clips(tmp_path: Path) -> list[Clip]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe required for local concatenate integration")
    clips = []
    for name, colour, audio in [("first", "red", True), ("second", "blue", False)]:
        path = tmp_path / f"{name}.mp4"
        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={colour}:s=64x64:r=24:d=2",
        ]
        if audio:
            args.extend(["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2"])
        args.extend(
            ["-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
        )
        subprocess.run(args, check=True, capture_output=True, timeout=30)
        clips.append(Clip(path))
    return clips


@pytest.mark.asyncio
async def test_real_concat_trims_and_preserves_audio(
    real_clips: list[Clip], tmp_path: Path
) -> None:
    from gflow_cli.selfhost.concatenate import probe

    clips = [Clip(real_clips[0].path, 0.2, 0.3), Clip(real_clips[1].path, 0.4, 0.5)]
    result = await execute(clips, tmp_path / "joined.mp4")
    metadata = await probe(result.path)
    assert result.bytes > 1000
    assert metadata.duration == pytest.approx(2.6, abs=0.12)
    assert (metadata.width, metadata.height) == (64, 64)
    assert metadata.has_audio
    assert result.path.read_bytes()[4:8] == b"ftyp"
    # A valid MP4 alone could hide reordered clips or discarded source audio.
    for timestamp, channel in [(0.5, 0), (2.1, 2)]:
        pixels = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(timestamp),
                "-i",
                str(result.path),
                "-frames:v",
                "1",
                "-vf",
                "scale=1:1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
        assert pixels[channel] > 200
    pcm = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(result.path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout
    samples = array("h", pcm)
    assert max(abs(sample) for sample in samples[:48000]) > 100
    assert max(abs(sample) for sample in samples[-24000:]) < 50


@pytest.mark.asyncio
async def test_missing_file_does_not_create_output(tmp_path: Path) -> None:
    output = tmp_path / "joined.mp4"
    with pytest.raises(ValueError, match="local file"):
        await execute([Clip(tmp_path / "missing.mp4"), Clip(tmp_path / "also-missing.mp4")], output)
    assert not output.exists()


@pytest.mark.asyncio
async def test_timeout_cleans_up_partial_output(real_clips: list[Clip], tmp_path: Path) -> None:
    output = tmp_path / "timeout.mp4"
    with pytest.raises(TimeoutError):
        await execute(real_clips, output, timeout_s=0)
    assert not output.exists()
    assert not list(tmp_path.glob(".timeout.*.mp4"))


@pytest.mark.asyncio
async def test_output_cannot_replace_input(real_clips: list[Clip]) -> None:
    original = real_clips[0].path.read_bytes()
    with pytest.raises(ValueError, match="replace a source"):
        await execute(real_clips, real_clips[0].path)
    assert real_clips[0].path.read_bytes() == original
