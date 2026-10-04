"""Strict private batch result projection; no remote bearer URLs or alias storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from gflow_cli.selfhost.concatenate import probe
from gflow_cli.selfhost.store import Store

MAX_VIDEO_BYTES = 256 * 1024 * 1024


async def publish_video_batch(
    store: Store, result: dict[str, Any], *, profile: str, project: str, out: Path, count: int
) -> dict[str, Any]:
    if (
        type(count) is not int
        or not 2 <= count <= 4
        or result.get("project_id") != project
        or type(result.get("returned_count")) is not int
        or result["returned_count"] != count
        or not isinstance(result.get("videos"), list)
        or len(result["videos"]) != count
    ):
        raise ValueError("Native video batch output cardinality/scope is unavailable")
    entries: list[tuple[str, str, Path | None]] = []
    used: set[str] = {project}
    for value in cast(list[Any], result["videos"]):
        if not isinstance(value, dict):
            raise ValueError("Native video batch item is unavailable")
        item = cast(dict[str, Any], value)
        media = str(UUID(item["media_id"]))
        workflow = str(UUID(item["workflow_id"]))
        if (
            item.get("project_id") != project
            or media in used
            or workflow in used
            or media == workflow
        ):
            raise ValueError("Native video batch output identities are inconsistent")
        used.update((media, workflow))
        if type(item.get("succeeded")) is not bool:
            raise ValueError("Native video batch status is unavailable")
        path = None
        if item["succeeded"]:
            path = Path(item["local_path"]).resolve()
            if (
                not path.is_relative_to(out.resolve())
                or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_VIDEO_BYTES
            ):
                raise ValueError("Native video batch artifact is unavailable")
            with path.open("rb") as stream:
                header = stream.read(12)
            if len(header) != 12 or header[4:8] != b"ftyp":
                raise ValueError("Native video batch artifact is not MP4")
            info = await probe(path, timeout_s=15)
            if info.width <= 0 or info.height <= 0 or info.duration <= 0:
                raise ValueError("Native video batch artifact metadata is unavailable")
            try:
                current = store.asset_get(media)
            except KeyError:
                current = None
            if current is not None and (
                current["profile"],
                current["project"],
                current["mime"],
            ) != (profile, project, "video/mp4"):
                raise ValueError("Native video batch artifact has another cached scope")
        elif item.get("local_path") is not None:
            raise ValueError("Failed native video batch clip cannot claim an artifact")
        entries.append((media, workflow, path))
    media_items: list[dict[str, Any]] = []
    for media, _workflow, path in entries:
        if path is None:
            continue
        path.chmod(0o600)
        store.asset_cache_if_scope(media, profile, project, str(path), "video/mp4")
        media_items.append(
            {
                "mediaGenerationId": media,
                "video": {"downloadPath": f"/v1/google-flow/assets/{media}/download"},
                "localArtifactId": media,
            }
        )
    output: dict[str, Any] = {
        "projectId": project,
        "media": media_items,
        "requestedCount": count,
        "completedCount": len(media_items),
        "knownMediaGenerationIds": [m for m, _, _ in entries],
        "workflowIds": [w for _, w, _ in entries],
    }
    if len(media_items) != count:
        output["error"] = {"code": "video_generation_failed", "retryable": False}
    provider = result.get("captchaProvider")
    if provider in ("CapSolver", "2Captcha", "supplied"):
        output["captchaProvider"] = provider
    return output


def interruption_checkpoint(path: Path, project: str) -> dict[str, Any] | None:
    """Only actual paired handles from the private worker dispatch checkpoint."""
    try:
        if not path.is_file() or path.stat().st_size > 16384:
            return None
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or cast(dict[str, Any], value).get("project_id") != project
            or cast(dict[str, Any], value).get("phase") not in ("video_submit", "video_poll")
            or not isinstance(cast(dict[str, Any], value).get("media_ids"), list)
            or not isinstance(cast(dict[str, Any], value).get("workflow_ids"), list)
        ):
            return None
        media = [str(UUID(identifier)) for identifier in cast(dict[str, Any], value)["media_ids"]]
        workflows = [
            str(UUID(identifier)) for identifier in cast(dict[str, Any], value)["workflow_ids"]
        ]
        if (
            len(media) != len(workflows)
            or len(media) > 4
            or len(set(media + workflows)) != len(media) * 2
            or project in media + workflows
        ):
            return None
        return {
            "projectId": project,
            "knownMediaGenerationIds": media,
            "outcomeUnknown": True,
            "error": {
                "code": "video_generation_outcome_unknown",
                "retryable": False,
                "phase": cast(dict[str, Any], value)["phase"],
                "media_ids": media,
                "workflow_ids": workflows,
            },
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
