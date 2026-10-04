"""Measured LWkPYd account history reads; stable observations, never full-history claims."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient

HISTORY_TIMEOUT_SECONDS = 45
PAGE_SIZE = 20


def _cursor(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 4096
        or not value.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise ValueError("Native history cursor requires 1 to 4096 printable ASCII characters")
    return value


def validate_history_options(
    cursor: object, all_pages: object, max_pages: object, max_media: object
) -> int:
    _cursor(cursor)
    if type(all_pages) is not bool:
        raise ValueError("all_pages must be a boolean")
    if max_pages is not None and (type(max_pages) is not int or not 1 <= max_pages <= 50):
        raise ValueError("max_pages must be an integer from 1 to 50")
    if not all_pages and max_pages is not None:
        raise ValueError("max_pages requires all_pages")
    if type(max_media) is not int or not 1 <= max_media <= 1000:
        raise ValueError("max_media must be an integer from 1 to 1000")
    return max_pages if max_pages is not None else (50 if all_pages else 1)


def validate_project_history_options(
    include_history: object,
    history_cursor: object,
    history_max_pages: object,
    history_max_media: object,
) -> tuple[str | None, int | None, int | None]:
    if type(include_history) is not bool:
        raise ValueError("include_history must be a boolean")
    if not include_history:
        if any(
            value is not None for value in (history_cursor, history_max_pages, history_max_media)
        ):
            raise ValueError("History controls require include_history")
        return None, None, None
    media = 1000 if history_max_media is None else history_max_media
    budget = validate_history_options(history_cursor, True, history_max_pages, media)
    return _cursor(history_cursor), budget, cast(int, media)


def parse_history_page(payload: object) -> dict[str, Any]:
    """Verify explicit account-page joins; strip captions, prompts and all URLs."""
    if not isinstance(payload, list) or len(cast(list[Any], payload)) != 3:
        raise ValueError("Native history page has an unsupported shape")
    values = cast(list[Any], payload)
    if not isinstance(values[0], list) or not isinstance(values[2], list):
        raise ValueError("Native history collections must be arrays")
    raw_workflows = cast(list[Any], values[0])
    raw_media = cast(list[Any], values[2])
    if len(raw_workflows) > PAGE_SIZE or len(raw_media) > 1000:
        raise ValueError("Native history page exceeds measured bounds")
    cursor = _cursor(values[1]) if values[1] not in (None, "") else None
    workflows: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    for candidate in raw_workflows:
        if not isinstance(candidate, list) or len(cast(list[Any], candidate)) < 5:
            raise ValueError("Native history workflow is malformed")
        row = cast(list[Any], candidate)
        identifier, project = validate_identifier(row[0]), validate_identifier(row[4])
        if identifier in owners:
            raise ValueError("Native history workflow identity is duplicated")
        owners[identifier] = project
        item: dict[str, Any] = {"workflow_id": identifier, "project_id": project}
        if not isinstance(row[3], list):
            raise ValueError("Native history workflow metadata is malformed")
        metadata = cast(list[Any], row[3])
        if len(metadata) > 4 and metadata[4] is not None:
            item["primary_media_id"] = validate_identifier(metadata[4])
        workflows.append(item)
    grouped: dict[str, list[Any]] = {}
    for candidate in raw_media:
        if not isinstance(candidate, list) or len(cast(list[Any], candidate)) < 3:
            raise ValueError("Native history media is malformed")
        row = cast(list[Any], candidate)
        project, workflow = validate_identifier(row[1]), validate_identifier(row[2])
        if owners.get(workflow) != project:
            raise ValueError("Native history media has unrelated workflow ownership")
        normalized = list(row)
        normalized[:3] = [validate_identifier(row[0]), project, workflow]
        grouped.setdefault(project, []).append(normalized)
    media: list[dict[str, Any]] = []
    for project, rows in grouped.items():
        media.extend(parse_media_snapshot([None, [], rows], project)["media"])
    media_by_id = {row["media_id"]: row for row in media}
    if len(media_by_id) != len(media):
        raise ValueError("Native history media identity is duplicated")
    for item in workflows:
        primary = item.get("primary_media_id")
        if primary is not None:
            related = media_by_id.get(primary)
            if related is None or (related["workflow_id"], related["project_id"]) != (
                item["workflow_id"],
                item["project_id"],
            ):
                raise ValueError("Native history primary media has unrelated ownership")
    return {"workflows": workflows, "media": media, "next_cursor": cursor}


async def history_snapshot(
    client: FlowApiClient,
    cursor: object = None,
    *,
    all_pages: bool = False,
    max_pages: int | None = None,
    max_media: int = 1000,
) -> dict[str, Any]:
    """One lease, bounded traversal; timeout returns only fully verified pages."""
    try:
        budget = validate_history_options(cursor, all_pages, max_pages, max_media)
    except ValueError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native history requires the migrated Flow host")
    current = _cursor(cursor)
    workflows: list[dict[str, Any]] = []
    media: list[dict[str, Any]] = []
    workflow_ids: set[str] = set()
    media_ids: set[str] = set()
    seen_cursors: set[str] = {current} if current is not None else set()
    pages_read = 0
    exhausted = capped = timed_out = False
    page: Any = None
    try:
        async with asyncio.timeout(HISTORY_TIMEOUT_SECONDS):
            page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
            if str(page.url).rstrip("/") != "https://flow.google.com/u/0":
                await page.goto("https://flow.google.com/u/0/", wait_until="domcontentloaded")
            await page.wait_for_function(
                "() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000
            )
            for _ in range(budget):
                data = await native_rpc(
                    page, "LWkPYd", [PAGE_SIZE, current], "/u/0/", require_single=True
                )
                result = parse_history_page(data)
                next_cursor = result["next_cursor"]
                if next_cursor is not None and next_cursor in seen_cursors:
                    raise ValueError("Native history cursor cycle")
                new_workflows = {row["workflow_id"] for row in result["workflows"]}
                new_media = {row["media_id"] for row in result["media"]}
                if workflow_ids & new_workflows or media_ids & new_media:
                    raise ValueError("Native history identity repeated across pages")
                if len(media) + len(result["media"]) > max_media:
                    capped = True
                    break  # Retain current request cursor; never skip truncated rows.
                workflows.extend(result["workflows"])
                media.extend(result["media"])
                workflow_ids.update(new_workflows)
                media_ids.update(new_media)
                pages_read += 1
                current = next_cursor
                if current is None:
                    exhausted = True
                    break
                seen_cursors.add(current)
            capped = capped or (not exhausted and pages_read == budget)
    except TimeoutError:
        if not pages_read:
            raise ConfigurationError(
                detail="Native history read timed out before a verified page"
            ) from None
        timed_out = True
    except ValueError as exc:
        raise WireFormatError(
            detail="Native history has an invalid shape", route="history.native"
        ) from exc
    finally:
        if page is not None:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
    return {
        "workflows": workflows,
        "media": media,
        "next_cursor": current,
        "pages_read": pages_read,
        "returned_count": len(workflows),
        "media_returned_count": len(media),
        "pagination_exhausted": exhausted,
        "complete": None,
        "capped": capped,
        "timed_out": timed_out,
        "scope": (
            "observed bounded native account history; snapshot consistency and completeness unknown"
        ),
    }
