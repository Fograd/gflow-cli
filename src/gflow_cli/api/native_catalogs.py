"""Explicit measured native inventory snapshots; no historical-envelope synthesis."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.transports.migrated_catalog import parse_native_voices
from gflow_cli.api.transports.migrated_projects import MAX_CURSOR_LENGTH, list_projects
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


def _dimensions(value: Any) -> dict[str, int]:
    if not isinstance(value, list) or len(cast("list[Any]", value)) < 2:
        return {}
    width, height = cast("list[Any]", value)[:2]
    if all(
        isinstance(n, int) and not isinstance(n, bool) and 0 < n <= 100000 for n in (width, height)
    ):
        return {"width": width, "height": height}
    return {}


def parse_media_snapshot(payload: Any, project_id: str) -> dict[str, Any]:
    """Classify only measured exclusive image/video arms; URLs never leave parser."""
    if not is_uuid(project_id):
        raise ValueError("Native project identifier must be a UUID")
    if not isinstance(payload, list) or len(cast("list[Any]", payload)) < 3:
        raise ValueError("Native project has no media collection")
    collection: Any = cast("list[Any]", payload)[2]
    if not isinstance(collection, list):
        raise ValueError("Native media collection must be an array")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in cast("list[Any]", collection):
        if not isinstance(candidate, list):
            raise ValueError("Native media row must be an array")
        row = cast("list[Any]", candidate)
        if len(row) < 3 or row[1] != project_id or not is_uuid(row[0]) or not is_uuid(row[2]):
            raise ValueError("Native media has unrelated or invalid identities")
        if row[0] in seen:
            raise ValueError("Native media identity is duplicated")
        seen.add(row[0])
        image: Any = row[6] if len(row) > 6 else None
        video: Any = row[7] if len(row) > 7 else None
        kind = "unknown"
        dimensions: dict[str, int] = {}
        if isinstance(image, list) and video is None:
            kind = "image"
            values = cast("list[Any]", image)
            dimensions = _dimensions(values[2] if len(values) > 2 else None)
        elif image is None and isinstance(video, list):
            kind = "video"
            values = cast("list[Any]", video)
            dimensions = _dimensions(values[1] if len(values) > 1 else None)
        rows.append(
            {
                "media_id": row[0],
                "project_id": project_id,
                "workflow_id": row[2],
                "kind": kind,
                **dimensions,
            }
        )
    return {
        "media": rows,
        "project_id": project_id,
        "returned_count": len(rows),
        "complete": None,
        "scope": "native project asset snapshot; completeness unknown",
    }


def _native_only(client: FlowApiClient) -> None:
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native inventory requires the migrated Flow host")


def validate_project_traversal(all_pages: object, max_pages: object) -> int:
    """Validate optional traversal before touching a browser/profile."""
    if type(all_pages) is not bool:
        raise ValueError("all_pages must be a boolean")
    if max_pages is not None and (type(max_pages) is not int or not 1 <= max_pages <= 100):
        raise ValueError("max_pages must be an integer from 1 to 100")
    if not all_pages and max_pages is not None:
        raise ValueError("max_pages requires all_pages")
    return max_pages if max_pages is not None else (100 if all_pages else 1)


async def projects_snapshot(
    client: FlowApiClient,
    cursor: object = None,
    *,
    all_pages: bool = False,
    max_pages: int | None = None,
) -> dict[str, Any]:
    _native_only(client)
    try:
        budget = validate_project_traversal(all_pages, max_pages)
    except ValueError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    if cursor is not None and (
        not isinstance(cursor, str) or not cursor or len(cursor) > MAX_CURSOR_LENGTH
    ):
        raise ConfigurationError(detail="Native project cursor requires 1 to 4096 characters")
    async with asyncio.timeout(180 if all_pages else 60):
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
        try:
            projects: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            seen_cursors: set[str] = {cursor} if cursor is not None else set()
            current = cursor
            exhausted = False
            pages_read = 0
            for _ in range(budget):
                result = await list_projects(page, current)
                pages_read += 1
                for row in result["projects"]:
                    identifier = str(row["project_id"]).lower()
                    if identifier in seen_ids:
                        raise ValueError("Duplicate native project identity during traversal")
                    seen_ids.add(identifier)
                    projects.append(row)
                current = result["next_cursor"]
                if current is None:
                    exhausted = True
                    break
                if current in seen_cursors:
                    raise ValueError("Native project cursor cycle")
                seen_cursors.add(current)
            scope = (
                "bounded native account project traversal"
                if all_pages
                else "one native account project page"
            )
            if cursor is not None:
                scope += "; continuation from supplied cursor"
            return {
                "projects": projects,
                "next_cursor": current,
                "returned_count": len(projects),
                "pages_read": pages_read,
                "pagination_exhausted": exhausted,
                "scope": scope,
                "complete": None,
            }
        except ValueError as exc:
            raise WireFormatError(
                detail="Native project listing has an invalid shape", route="projects.native"
            ) from exc
        finally:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def media_snapshot(client: FlowApiClient, project_id: str) -> dict[str, Any]:
    _native_only(client)
    if not is_uuid(project_id):
        raise ConfigurationError(detail="Native project identifier must be a UUID")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        return parse_media_snapshot(await read_project_payload(page, project_id), project_id)
    except ValueError as exc:
        raise WireFormatError(
            detail="Native media listing has an invalid shape", route="media.native"
        ) from exc
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def voices_snapshot(client: FlowApiClient, project_id: str) -> dict[str, Any]:
    """Read measured native system presets; custom voices and completeness unknown."""
    _native_only(client)
    if not is_uuid(project_id):
        raise ConfigurationError(detail="Native project identifier must be a UUID")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        rows = parse_native_voices(await read_project_payload(page, project_id))
        voices = [
            {
                "name": row["voice"],
                "description": row["description"],
                "sample_url": row.get("sample_url"),
                "source": "system",
            }
            for row in rows
        ]
        return {
            "voices": voices,
            "project_id": project_id,
            "catalog": "google",
            "returned_count": len(voices),
            "complete": None,
            "scope": "native project system preset voice snapshot; completeness unknown",
        }
    except ValueError as exc:
        raise WireFormatError(
            detail="Native voice listing has an invalid shape", route="voices.native"
        ) from exc
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
