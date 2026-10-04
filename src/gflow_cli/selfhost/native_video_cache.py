"""Bounded private MP4 caching after fresh native ownership proof."""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from gflow_cli.selfhost.concatenate import probe
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import contained_file, parse_json_output
from gflow_cli.selfhost.store import Store

MAX_VIDEO_CACHE_BYTES = 256 * 1024 * 1024


def verified_cache_account(cfg: Settings, store: Store, profile: str) -> None:
    configured = cfg.accounts.get(profile)
    row = next((item for item in store.accounts() if item["profile"] == profile), None)
    if (
        configured is None
        or row is None
        or row["email"] != configured["email"]
        or row["enabled"] != 1
        or row["verified"] != 1
        or store.resolve_profile_scope(profile, configured["email"]) != profile
    ):
        raise ValueError("Native video cache requires a current verified account")


async def _verified_file(path: Path, metadata: dict[str, Any]) -> None:
    size = path.stat().st_size
    if not 0 < size <= MAX_VIDEO_CACHE_BYTES:
        raise ValueError("Native cached video exceeds the byte cap")
    with path.open("rb") as stream:
        head = stream.read(12)
    if len(head) != 12 or head[4:8] != b"ftyp":
        raise ValueError("Native cached video is not an MP4")
    dimensions = (metadata.get("width"), metadata.get("height"))
    if any(type(value) is not int or value <= 0 for value in dimensions):
        raise ValueError("Native video dimensions are unavailable")
    info = await probe(path, timeout_s=15)
    if (info.width, info.height) != dimensions:
        raise ValueError("Native video bytes do not match fresh metadata")


async def cache_native_video(
    cfg: Settings,
    store: Store,
    profile: str,
    project: str,
    identifier: str,
    metadata: dict[str, Any],
    run: Callable[[list[str], int], Awaitable[tuple[int, bytes]]],
) -> None:
    """Publish only exact bounded worker results; foreign rows are never replaced."""
    verified_cache_account(cfg, store, profile)
    try:
        current = store.asset_get(identifier)
    except KeyError:
        current = None
    if current is not None:
        if (current["profile"], current["project"], current["mime"]) != (
            profile,
            project,
            "video/mp4",
        ):
            raise ValueError("Native video cache has another scope or media kind")
        await _verified_file(contained_file(current["path"], cfg.root), metadata)
        return
    parent = cfg.root / "native-video-cache" / profile / project
    if not parent.resolve().is_relative_to(cfg.root.resolve()):
        raise ValueError("Native video cache is outside its private root")
    for directory in (cfg.root / "native-video-cache", parent.parent, parent):
        directory.mkdir(exist_ok=True, mode=0o700)
    output = parent / str(uuid.uuid4())
    output.mkdir(mode=0o700)
    published = False
    try:
        code, raw = await run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "asset-download",
                profile,
                json.dumps(
                    {"project_id": project, "media_id": identifier, "output_dir": str(output)}
                ),
            ],
            90,
        )
        result = parse_json_output(raw)
        if (
            code
            or result.get("status") != "ok"
            or result.get("kind") != "video"
            or result.get("mediaGenerationId") != identifier
            or result.get("projectId") != project
            or result.get("mimeType") != "video/mp4"
            or type(result.get("bytes")) is not int
            or not 0 < result["bytes"] <= MAX_VIDEO_CACHE_BYTES
        ):
            raise ValueError("Native video cache result is unavailable")
        path = contained_file(str(result.get("path", "")), output)
        if path.parent != output.resolve() or path.stat().st_size != result["bytes"]:
            raise ValueError("Native video cache bytes are unavailable")
        await _verified_file(path, metadata)
        path.chmod(0o600)
        verified_cache_account(cfg, store, profile)
        published = store.asset_cache_if_scope(identifier, profile, project, str(path), "video/mp4")
    finally:
        if not published:
            shutil.rmtree(output)
