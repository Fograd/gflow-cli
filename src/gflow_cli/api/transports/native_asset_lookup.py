"""Exact existing-media lookup, separate from generation acknowledgement codecs.

Current as29s identity order is media/project/workflow. Protected URLs are
transient bearer credentials; never include this result in routine logging.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.native_voices import saved_voice_detail_fields, validate_identifier


@dataclass(frozen=True)
class NativeAsset:
    media_id: str
    project_id: str
    workflow_id: str
    kind: Literal["image", "video"]
    url: str = field(repr=False)
    width: int | None
    height: int | None
    size_bytes: int | None = None


@dataclass(frozen=True)
class NativeAudioAsset:
    """Confidential playback metadata; audio has no image/video dimensions."""

    media_id: str
    project_id: str
    workflow_id: str
    url: str = field(repr=False)
    kind: Literal["audio"] = field(default="audio", init=False)
    width: None = field(default=None, init=False)
    height: None = field(default=None, init=False)


def _owned_audio_workflow(payload: Any, project: str, workflow: str) -> None:
    rows = _list(_at(payload, 1))
    matches = [row for row in rows if _at(row, 0) == workflow]
    if len(matches) != 1:
        raise ValueError("Native audio workflow ownership is unresolved")
    row = _list(matches[0])
    info = _list(_at(row, 3))
    if _at(row, 4) != project or len(info) < 5 or info[2]:
        raise ValueError("Native audio requires an active owned project workflow")


def _existing_audio(payload: Any, project: str, media: str, workflow: str) -> NativeAudioAsset:
    if len({project, media, workflow}) != 3:
        raise ValueError("Native audio identities must be distinct")
    fields = saved_voice_detail_fields(
        payload, project_id=project, media_id=media, workflow_id=workflow
    )
    url = fields.get("audio_url")
    if not isinstance(url, str):
        raise ValueError("Native audio playback URL is unavailable")
    return NativeAudioAsset(media, project, workflow, url)


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Native asset metadata has an unsupported shape")
    return cast(list[Any], value)


def _at(value: Any, *indices: int) -> Any:
    for index in indices:
        if not isinstance(value, list) or len(cast(list[Any], value)) <= index:
            return None
        value = cast(list[Any], value)[index]
    return value


def media_url(value: Any, kind: Literal["image", "video"]) -> str:
    if not isinstance(value, str):
        raise ValueError("Native asset original URL is unavailable")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "flow-content.google"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not parsed.path.startswith("/" + kind + "/")
            or parsed.fragment
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Native asset URL is outside the measured media boundary") from None
    return value


def existing_asset(
    payload: Any,
    *,
    project_id: str,
    media_id: str,
    workflow_id: str,
    kind: Literal["image", "video"],
) -> NativeAsset:
    project, media, workflow = (validate_identifier(v) for v in (project_id, media_id, workflow_id))
    if kind not in ("image", "video"):
        raise ValueError("Native asset lookup supports image or video")
    row = _list(payload)
    if (
        len(row) < 7
        or row[:3] != [media, project, workflow]
        or len({media, project, workflow}) != 3
    ):
        raise ValueError("Native asset identity does not match the fresh owned snapshot")
    arms = [_at(row, i) for i in (6, 7, 10)]
    selected = 0 if kind == "image" else 1
    if any(value is not None for i, value in enumerate(arms) if i != selected):
        raise ValueError("Native asset media union is ambiguous or has the wrong kind")
    arm = _list(arms[selected])
    dimensions = _list(_at(arm, 2 if kind == "image" else 1))
    absent_video_dimensions = kind == "video" and dimensions[:2] == [None, None]
    if not absent_video_dimensions and (
        len(dimensions) < 2
        or not all(
            isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 100000
            for v in dimensions[:2]
        )
    ):
        raise ValueError("Native asset dimensions are unavailable")
    generated = _at(arm, 0)
    uploaded = _at(arm, 1 if kind == "image" else 4)
    if (generated is None) == (uploaded is None):
        raise ValueError("Native asset original media arm is unavailable or ambiguous")
    source = _list(generated if generated is not None else uploaded)
    index = (
        (13 if kind == "image" else 8) if generated is not None else (3 if kind == "image" else 2)
    )
    url = media_url(_at(source, index), kind)
    size = _at(row, 5, 13)
    expected_size = (
        size if isinstance(size, int) and not isinstance(size, bool) and size > 0 else None
    )
    return NativeAsset(
        media, project, workflow, kind, url, dimensions[0], dimensions[1], expected_size
    )


async def lookup_asset(
    page: Any, *, project_id: str, media_id: str
) -> NativeAsset | NativeAudioAsset:
    """One page, fresh ownership projection and one strict correlated metadata read."""
    project, media = validate_identifier(project_id), validate_identifier(media_id)
    async with asyncio.timeout(60):
        project_payload = await read_project_payload(page, project)
        snapshot = parse_media_snapshot(project_payload, project)
        matches = [row for row in snapshot["media"] if row["media_id"] == media]
        if len(matches) != 1 or matches[0]["kind"] not in ("image", "video", "audio"):
            raise ValueError("Native media is unresolved in the fresh selected-project snapshot")
        owned = matches[0]
        if owned["kind"] == "audio":
            _owned_audio_workflow(project_payload, project, owned["workflow_id"])
        payload = await native_rpc(
            page, "as29s", [media], "/project/" + project, require_single=True
        )
        if owned["kind"] == "audio":
            return _existing_audio(payload, project, media, owned["workflow_id"])
        return existing_asset(
            payload,
            project_id=project,
            media_id=media,
            workflow_id=owned["workflow_id"],
            kind=owned["kind"],
        )
