"""Native account project discovery using the measured paginated UpteDb contract."""

from __future__ import annotations

from typing import Any, cast

from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.migrated_video_upload import is_uuid

MAX_CURSOR_LENGTH = 4096


def parse_projects(payload: object) -> dict[str, Any]:
    """Return stable metadata only; signed poster URLs never enter the registry."""
    if not isinstance(payload, list):
        raise ValueError("Native project listing is not an array")
    values = cast("list[Any]", payload)
    if not values:
        return {"projects": [], "next_cursor": None}
    if not isinstance(values[0], list):
        raise ValueError("Native project listing has no project rows")
    cursor = values[1] if len(values) > 1 else None
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > MAX_CURSOR_LENGTH):
        raise ValueError("Native project continuation has an unsupported shape")
    projects: list[dict[str, Any]] = []
    for value in cast("list[Any]", values[0]):
        if not isinstance(value, list):
            raise ValueError("Native project row is not an array")
        row = cast("list[Any]", value)
        if len(row) < 2 or not is_uuid(row[0]) or not isinstance(row[1], list):
            raise ValueError("Native project row has invalid identity or metadata")
        detail = cast("list[Any]", row[1])
        if not detail or not isinstance(detail[0], str):
            raise ValueError("Native project row has no display name")
        item: dict[str, Any] = {"project_id": row[0], "name": detail[0]}
        if len(detail) > 2 and isinstance(detail[2], list):
            stamp = cast("list[Any]", detail[2])
            if stamp and isinstance(stamp[0], int) and not isinstance(stamp[0], bool):
                item["modified_seconds"] = stamp[0]
                if len(stamp) > 1 and isinstance(stamp[1], int) and not isinstance(stamp[1], bool):
                    item["modified_nanos"] = stamp[1]
        if len(detail) > 4 and is_uuid(detail[4]):
            item["last_media_id"] = detail[4]
        projects.append(item)
    return {"projects": projects, "next_cursor": cursor or None}


async def list_projects(page: Any, cursor: object = None) -> dict[str, Any]:
    """Read one native account page; continuation stays opaque and is never guessed."""
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > MAX_CURSOR_LENGTH):
        raise ValueError("Project cursor must be an opaque string of at most 4096 characters")
    if str(page.url).rstrip("/") != "https://flow.google.com/u/0":
        await page.goto("https://flow.google.com/u/0/")
    await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
    payload = await native_rpc(
        page, "UpteDb", ["projects/*", 21, cursor, None, None, None, [1]], "/u/0/"
    )
    return parse_projects(payload)
