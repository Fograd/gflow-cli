"""Explicit measured native inventory snapshots; no historical-envelope synthesis."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.transports.migrated_catalog import parse_native_characters, parse_native_voices
from gflow_cli.api.transports.migrated_projects import MAX_CURSOR_LENGTH, list_projects
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.api.transports.native_voices import parse_saved_voices, validate_identifier
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


def _source_created_time(row: list[Any]) -> dict[str, str]:
    metadata: Any = row[5] if len(row) > 5 else None
    if not isinstance(metadata, list):
        return {}
    values = cast(list[Any], metadata)
    stamp: Any = values[0] if values else None
    if not isinstance(stamp, list) or not stamp:
        return {}
    parts = cast(list[Any], stamp)
    seconds: Any = parts[0]
    nanos: Any = parts[1] if len(parts) > 1 else 0
    if (
        isinstance(seconds, str)
        and 1 <= len(seconds) <= 12
        and seconds.isascii()
        and seconds.isdecimal()
    ):
        seconds = int(seconds)
    if type(seconds) is not int or not 0 <= seconds <= 253402300799:
        return {}
    if type(nanos) is not int or not 0 <= nanos <= 999999999:
        return {}
    base = datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")[:-6]
    fraction = ("." + f"{nanos:09d}".rstrip("0")) if nanos else ""
    return {"created_time": base + fraction + "Z"}


def _likely_uploaded_media(kind: str, image: Any, video: Any) -> bool:
    arm = image if kind == "image" else video if kind == "video" else None
    upload_index = 1 if kind == "image" else 4
    if not isinstance(arm, list):
        return False
    values = cast(list[Any], arm)
    uploaded: Any = values[upload_index] if len(values) > upload_index else None
    return (
        values[0] is None and isinstance(uploaded, list) and len(cast(list[Any], uploaded)) > 0
        if values
        else False
    )


def _bundled_preset_attachment(wrapper: list[Any]) -> bool:
    from gflow_cli.api.character import VOICE_NAMES

    name: Any = wrapper[2]
    identifier: Any = wrapper[0]
    if type(wrapper[1]) is not int or wrapper[1] != 3 or name not in VOICE_NAMES:
        return False
    if not isinstance(identifier, str) or identifier.casefold() != name.casefold():
        return False
    details: Any = wrapper[3]
    if not isinstance(details, list):
        return False
    values = cast(list[Any], details)
    if (
        len(values) <= 10
        or not isinstance(values[0], str)
        or values[0].casefold() != name.casefold()
    ):
        return False
    samples: Any = values[10]
    if not isinstance(samples, list) or not samples:
        return False
    sample: Any = cast(list[Any], samples)[0]
    if not isinstance(sample, list):
        return False
    source = cast(list[Any], sample)
    return (
        len(source) >= 4
        and source[0] == name
        and source[3] == f"https://gstatic.com/aitestkitchen/voices/samples/{name}.wav"
    )


def parse_media_snapshot(
    payload: Any, project_id: str, *, include_attached: bool = False
) -> dict[str, Any]:
    """Classify measured exclusive image/video/audio arms; URLs never leave parser."""
    if not is_uuid(project_id):
        raise ValueError("Native project identifier must be a UUID")
    if not isinstance(payload, list) or len(cast("list[Any]", payload)) < 3:
        raise ValueError("Native project has no media collection")
    collection: Any = cast("list[Any]", payload)[2]
    if not isinstance(collection, list):
        raise ValueError("Native media collection must be an array")
    if type(include_attached) is not bool:
        raise ValueError("include_attached must be a boolean")
    values = cast(list[Any], payload)
    candidates: list[tuple[Any, bool]] = [(row, False) for row in cast(list[Any], collection)]
    if include_attached and len(values) > 3 and values[3] is not None:
        attached: Any = values[3]
        if not isinstance(attached, list):
            raise ValueError("Native attached media collection must be an array")
        for wrapper in cast(list[Any], attached):
            if not isinstance(wrapper, list) or len(cast(list[Any], wrapper)) < 4:
                raise ValueError("Native attached media wrapper is malformed")
            wrapper_values = cast(list[Any], wrapper)
            if _bundled_preset_attachment(wrapper_values):
                continue
            if wrapper_values[3] is not None:
                candidates.append((wrapper_values[3], True))
    rows: list[dict[str, Any]] = []
    seen: dict[str, list[Any]] = {}
    for candidate, attached_row in candidates:
        if not isinstance(candidate, list):
            raise ValueError("Native media row must be an array")
        row = cast("list[Any]", candidate)
        if (
            len(row) < 3
            or not is_uuid(row[1])
            or (not attached_row and row[1] != project_id)
            or not is_uuid(row[0])
            or not is_uuid(row[2])
        ):
            raise ValueError("Native media has unrelated or invalid identities")
        if row[0] in seen:
            if include_attached and row == seen[row[0]]:
                continue
            raise ValueError("Native media identity is duplicated or contradictory")
        seen[row[0]] = row
        image: Any = row[6] if len(row) > 6 else None
        video: Any = row[7] if len(row) > 7 else None
        audio: Any = row[10] if len(row) > 10 else None
        kind = "unknown"
        dimensions: dict[str, int] = {}
        if isinstance(image, list) and video is None and audio is None:
            kind = "image"
            values = cast("list[Any]", image)
            dimensions = _dimensions(values[2] if len(values) > 2 else None)
        elif image is None and isinstance(video, list) and audio is None:
            kind = "video"
            values = cast("list[Any]", video)
            dimensions = _dimensions(values[1] if len(values) > 1 else None)
        elif image is None and video is None and isinstance(audio, list):
            kind = "audio"
        rows.append(
            {
                "media_id": row[0],
                "project_id": row[1],
                "workflow_id": row[2],
                "kind": kind,
                **({"attached_to_project_id": project_id} if attached_row else {}),
                **(
                    {"likely_upload": _likely_uploaded_media(kind, image, video)}
                    if include_attached
                    else {}
                ),
                **(_source_created_time(row) if include_attached else {}),
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


def validate_project_catalogs(include_catalogs: object, max_projects: object) -> int:
    """Bound read-only project enrichment independently of account pagination."""
    if type(include_catalogs) is not bool:
        raise ValueError("include_catalogs must be a boolean")
    if max_projects is not None and (type(max_projects) is not int or not 1 <= max_projects <= 20):
        raise ValueError("max_projects must be an integer from 1 to 20")
    if not include_catalogs and max_projects is not None:
        raise ValueError("max_projects requires include_catalogs")
    return max_projects if max_projects is not None else 20


def project_catalog_snapshot(payload: Any, project_id: str) -> dict[str, Any]:
    """One fresh owned payload, URL-free typed observations with exact row counts."""
    project = validate_identifier(project_id)
    media = parse_media_snapshot(payload, project, include_attached=True)["media"]
    workflows = project_media(payload, project)
    seen_workflows: set[str] = set()
    for candidate in payload[1]:
        if not isinstance(candidate, list):
            raise ValueError("Native catalog workflow ownership is unavailable")
        row = cast(list[Any], candidate)
        if len(row) < 5 or row[4] != project:
            raise ValueError("Native catalog workflow ownership is unavailable")
        identifier = validate_identifier(row[0])
        if identifier in seen_workflows:
            raise ValueError("Native catalog workflow identity is duplicated")
        seen_workflows.add(identifier)
    characters = parse_native_characters(payload, project)
    voices = parse_saved_voices(payload, project)
    for rows, field in ((media, "media_id"), (characters, "entity_id"), (voices, "ref")):
        identifiers = [validate_identifier(row[field]) for row in rows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Native catalog identity is duplicated")
    return {
        "project_id": project,
        "media": media,
        "workflows": workflows,
        "characters": characters,
        "user_voices": voices,
        "counts": {
            "media": len(media),
            "workflows": len(workflows),
            "characters": len(characters),
            "user_voices": len(voices),
        },
        "complete": None,
        "scope": "observed native project catalogs; workflow history and completeness unknown",
    }


async def projects_snapshot(
    client: FlowApiClient,
    cursor: object = None,
    *,
    all_pages: bool = False,
    max_pages: int | None = None,
    include_catalogs: bool = False,
    max_projects: int | None = None,
) -> dict[str, Any]:
    _native_only(client)
    try:
        budget = validate_project_traversal(all_pages, max_pages)
        catalog_budget = validate_project_catalogs(include_catalogs, max_projects)
    except ValueError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    if cursor is not None and (
        not isinstance(cursor, str) or not cursor or len(cursor) > MAX_CURSOR_LENGTH
    ):
        raise ConfigurationError(detail="Native project cursor requires 1 to 4096 characters")
    async with asyncio.timeout(180 if all_pages or include_catalogs else 60):
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
            output: dict[str, Any] = {
                "projects": projects,
                "next_cursor": current,
                "returned_count": len(projects),
                "pages_read": pages_read,
                "pagination_exhausted": exhausted,
                "scope": scope,
                "complete": None,
            }
            if include_catalogs:
                catalogs: list[dict[str, Any]] = []
                counts = {"media": 0, "workflows": 0, "characters": 0, "user_voices": 0}
                for row in projects[:catalog_budget]:
                    payload = await read_project_payload(page, row["project_id"])
                    catalog = project_catalog_snapshot(payload, row["project_id"])
                    catalogs.append(catalog)
                    for field in counts:
                        counts[field] += catalog["counts"][field]
                pending = [row["project_id"] for row in projects[catalog_budget:]]
                output.update(
                    {
                        "project_catalogs": catalogs,
                        "catalog_projects_read": len(catalogs),
                        "catalog_counts": counts,
                        "pending_project_ids": pending,
                        "catalogs_capped": bool(pending),
                    }
                )
            return output
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
        return parse_media_snapshot(
            await read_project_payload(page, project_id), project_id, include_attached=True
        )
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
