"""Fresh character image detail using measured owned workflow relationships."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.native_asset_lookup import existing_asset
from gflow_cli.api.transports.native_voices import get_saved_voice, validate_identifier


def character_image_handles(payload: Any, *, project_id: str, entity_id: str) -> dict[str, Any]:
    project, entity = validate_identifier(project_id), validate_identifier(entity_id)
    matches = [
        row for row in parse_native_characters(payload, project) if row["entity_id"] == entity
    ]
    if len(matches) != 1:
        raise ValueError("Character is unresolved or ambiguous in the selected project")
    character = matches[0]
    references = character["workflow_ids"]
    if len(references) != len(set(references)):
        raise ValueError("Character references are ambiguous")
    if len(references) > 16:
        raise ValueError("Character detail exceeds the bounded read budget")
    media = parse_media_snapshot(payload, project)["media"]
    handles: list[dict[str, str]] = []
    for workflow in references:
        workflows: list[list[Any]] = [
            cast(list[Any], row)
            for row in payload[1]
            if isinstance(row, list) and row and row[0] == workflow
        ]
        if len(workflows) != 1:
            raise ValueError("Character workflow is unresolved or ambiguous")
        owned = workflows[0]
        if (
            len(owned) < 6
            or owned[4] != project
            or owned[5] != entity
            or not isinstance(owned[3], list)
            or len(cast(list[Any], owned[3])) < 5
            or owned[3][2]
        ):
            raise ValueError("Character workflow ownership does not match")
        primary = validate_identifier(cast(list[Any], owned[3])[4])
        # A missing projection is not evidence of missing media. This handle
        # remains a candidate until strict GetMedia verifies its full triple/type.
        rows = [row for row in media if row["media_id"] == primary]
        if rows and (
            len(rows) != 1 or rows[0]["workflow_id"] != workflow or rows[0]["kind"] != "image"
        ):
            raise ValueError("Character primary image projection contradicts ownership")
        handles.append({"workflow_id": workflow, "media_id": primary})
    if len({handle["media_id"] for handle in handles}) != len(handles):
        raise ValueError("Character primary identities are ambiguous")
    thumbnail = character.get("thumbnail_media_id")
    thumbnails = [handle for handle in handles if handle["media_id"] == thumbnail]
    if thumbnail is not None and not thumbnails:
        rows = [row for row in media if row["media_id"] == thumbnail and row["kind"] == "image"]
        if len(rows) != 1:
            raise ValueError("Character thumbnail ownership is unresolved")
        workflow = rows[0]["workflow_id"]
        workflows = [
            row for row in payload[1] if isinstance(row, list) and row and row[0] == workflow
        ]
        if len(workflows) != 1:
            raise ValueError("Character thumbnail workflow is ambiguous")
        owned = workflows[0]
        if (
            len(owned) < 6
            or owned[4] != project
            or owned[5] != entity
            or not isinstance(owned[3], list)
            or len(cast(list[Any], owned[3])) < 3
            or owned[3][2]
        ):
            raise ValueError("Character thumbnail workflow ownership does not match")
        thumbnails = [{"workflow_id": workflow, "media_id": thumbnail}]
    if len({handle["media_id"] for handle in [*handles, *thumbnails]}) > 16:
        raise ValueError("Character detail exceeds the bounded read budget")
    return {
        "character": character,
        "references": handles,
        "thumbnail": thumbnails[0] if thumbnails else None,
    }


async def lookup_character(
    page: Any, *, project_id: str, entity_id: str | None = None, name: str | None = None
) -> dict[str, Any]:
    """One snapshot and one strict metadata read per distinct ordered image."""
    project = validate_identifier(project_id)
    if (entity_id is None) == (name is None):
        raise ValueError("Provide exactly one character ID or exact name")
    if entity_id is not None:
        entity_id = validate_identifier(entity_id)
    async with asyncio.timeout(60):
        payload = await read_project_payload(page, project)
        matches = [
            row
            for row in parse_native_characters(payload, project)
            if (
                row["entity_id"] == entity_id
                if entity_id is not None
                else row["display_name"] == name
            )
        ]
        if len(matches) != 1:
            raise ValueError("Character selector is unresolved or ambiguous")
        joined = character_image_handles(
            payload, project_id=project, entity_id=matches[0]["entity_id"]
        )
        result = dict(joined["character"])
        references: list[dict[str, str]] = []
        thumbnail = joined["thumbnail"]
        distinct = list(joined["references"])
        if thumbnail is not None and not any(
            row["media_id"] == thumbnail["media_id"] for row in distinct
        ):
            distinct.append(thumbnail)
        urls: dict[str, str] = {}
        for handle in distinct:
            detail = await native_rpc(
                page,
                "as29s",
                [handle["media_id"]],
                "/project/" + project,
                require_single=True,
            )
            asset = existing_asset(
                detail,
                project_id=project,
                media_id=handle["media_id"],
                workflow_id=handle["workflow_id"],
                kind="image",
            )
            urls[handle["media_id"]] = asset.url
        references = [
            {**handle, "preview_url": urls[handle["media_id"]]} for handle in joined["references"]
        ]
        result["image_references"] = references
        if thumbnail is not None:
            result["thumbnail_url"] = urls[thumbnail["media_id"]]
        voice = result.get("voice")
        if voice:
            if result.get("preset_voice_id"):
                result["voice_detail"] = {"source": "system", "voice": voice, "display_name": voice}
            else:
                saved = await get_saved_voice(page, project, voice)
                result["voice_detail"] = {"source": "user", "voice": voice, **saved}
        return result
