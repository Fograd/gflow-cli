"""Local MP4 concatenation for managed videos; no Google generation or joining.

The caller resolves authenticated media IDs to contained local paths. This module
accepts those paths only, invokes FFmpeg without a shell, and normalises the join
into H.264/30fps plus AAC/48kHz stereo. Missing audio becomes silence.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


@dataclass(frozen=True)
class Clip:
    """A trusted managed video and seconds removed from either end."""

    path: Path
    trim_start: float = 0
    trim_end: float = 0


@dataclass(frozen=True)
class VideoInfo:
    """Minimal metadata needed to validate and assemble a join."""

    duration: float
    width: int
    height: int
    has_audio: bool
    sample_aspect_ratio: str = "1:1"


@dataclass(frozen=True)
class ConcatenateResult:
    """A completed, atomically published local MP4."""

    path: Path
    bytes: int
    duration: float
    width: int
    height: int


async def _run(args: Sequence[str], timeout_s: float) -> bytes:
    """Run our own subprocess with cancellation/timeout cleanup and safe errors."""
    try:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg and ffprobe must be installed for local concatenation") from exc
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError("Local media processing failed; verify that the source is a valid video")
    return stdout


async def probe(path: Path, *, timeout_s: float = 30) -> VideoInfo:
    """Read bounded metadata from a local file, without accepting remote URLs."""
    if not path.is_file():
        raise ValueError("Each clip must refer to an existing managed local file")
    raw = await _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,sample_aspect_ratio",
            "-of",
            "json",
            str(path.resolve()),
        ],
        timeout_s,
    )
    if len(raw) > 1024 * 1024:
        raise ValueError("Source video metadata exceeds the size cap")
    try:
        payload = cast("dict[str, Any]", json.loads(raw))
        streams = cast("list[dict[str, Any]]", payload["streams"])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        info = VideoInfo(
            duration=float(payload["format"]["duration"]),
            width=int(video["width"]),
            height=int(video["height"]),
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
            sample_aspect_ratio=str(video.get("sample_aspect_ratio", "1:1")),
        )
    except (ValueError, TypeError, KeyError, StopIteration) as exc:
        raise ValueError("Source must contain video and a known finite duration") from exc
    return info


def validate(clips: Sequence[Clip], metadata: Sequence[VideoInfo]) -> None:
    """Validate useapi-style clip/trim bounds and compatible output dimensions."""
    if not 2 <= len(clips) <= 10:
        raise ValueError("Concatenation requires 2 to 10 clips")
    if len(metadata) != len(clips):
        raise ValueError("Each clip requires video metadata")
    dimensions = (metadata[0].width, metadata[0].height)
    for clip, info in zip(clips, metadata, strict=True):
        if not math.isfinite(info.duration) or info.duration <= 0:
            raise ValueError("Source video duration must be positive and finite")
        if (info.width, info.height) != dimensions:
            raise ValueError("All clips must have identical dimensions and aspect ratio")
        if info.width <= 0 or info.height <= 0 or info.width % 2 or info.height % 2:
            raise ValueError("Video dimensions must be positive even values for H.264 export")
        if info.sample_aspect_ratio not in ("1:1", "N/A"):
            raise ValueError("Local concatenate supports square-pixel source videos only")
        for trim in (clip.trim_start, clip.trim_end):
            if not math.isfinite(trim) or not 0 <= trim <= 10:
                raise ValueError("Each trim must be a finite number between 0 and 10 seconds")
        if clip.trim_start + clip.trim_end >= info.duration:
            raise ValueError("Combined trims must be less than the source video duration")


async def execute(
    clips: Sequence[Clip], output: Path, *, timeout_s: float = 300
) -> ConcatenateResult:
    """Trim and join videos into one atomically written managed MP4.

    Raises ValueError for invalid input, RuntimeError for unavailable tools or
    invalid media, and TimeoutError on processing timeout. Source paths and output
    containment belong to the authenticated registry caller, never to HTTP input.
    """
    if not 2 <= len(clips) <= 10:
        raise ValueError("Concatenation requires 2 to 10 clips")
    metadata = [await probe(clip.path) for clip in clips]
    validate(clips, metadata)
    destination = output.resolve()
    if any(destination == clip.path.resolve() for clip in clips):
        raise ValueError("Output must not replace a source video")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.{uuid4().hex}.mp4")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for clip in clips:
        args.extend(["-protocol_whitelist", "file,pipe", "-i", str(clip.path.resolve())])
    filters: list[str] = []
    joins: list[str] = []
    for index, (clip, info) in enumerate(zip(clips, metadata, strict=True)):
        length = info.duration - clip.trim_start - clip.trim_end
        end = info.duration - clip.trim_end
        filters.append(
            f"[{index}:v:0]trim=start={clip.trim_start}:end={end},"
            f"setpts=PTS-STARTPTS,setsar=1,fps=30,format=yuv420p[v{index}]"
        )
        if info.has_audio:
            filters.append(
                f"[{index}:a:0]atrim=start={clip.trim_start}:end={end},"
                f"asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                f"apad,atrim=duration={length}[a{index}]"
            )
        else:
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={length},asetpts=PTS-STARTPTS[a{index}]"
            )
        joins.extend([f"[v{index}]", f"[a{index}]"])
    filters.append("".join(joins) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
    args.extend(
        [
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(temporary),
        ]
    )
    try:
        await _run(args, timeout_s)
        result_info = await probe(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return ConcatenateResult(
        path=destination,
        bytes=destination.stat().st_size,
        duration=result_info.duration,
        width=result_info.width,
        height=result_info.height,
    )
