"""Measured native character metadata operations; no portrait or voice generation."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import uuid4

from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.migrated_video_upload import is_uuid

POST_MUTATION_TIMEOUT = 45.0


class CharacterBindingError(ValueError):
    """Creation succeeded but binding needs inspection; never blindly create again."""

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        super().__init__("Character created but image binding failed; inspect before retrying")


class CharacterDeletionError(ValueError):
    """Deletion may have succeeded; inspect instead of blindly submitting again."""

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        super().__init__("Character deletion outcome unknown; inspect before retrying")


async def _rpc(page: Any, project_id: str, rpc: str, args: list[Any]) -> Any:
    return await native_rpc(page, rpc, args, "/project/" + project_id)


def update_payload(
    project_id: str, entity_id: str, name: object = None, personality: object = None
) -> list[Any]:
    if not is_uuid(project_id) or not is_uuid(entity_id):
        raise ValueError("Character identifiers must be UUIDs")
    if name is None and personality is None:
        raise ValueError("At least one character metadata field is required")
    if name is not None and (not isinstance(name, str) or not 1 <= len(name) <= 200):
        raise ValueError("Character name must contain 1 to 200 characters")
    if personality is not None and (not isinstance(personality, str) or len(personality) > 4000):
        raise ValueError("Personality must be a string of at most 4000 characters")
    paths: list[str] = []
    if name is not None:
        paths.append("entity_info.display_name")
    if personality is not None:
        paths.append("entity_info.character_info.personality_notes")
    info: list[Any] = [1, name]
    if personality is not None:
        info.append([None, None, personality])
    return [[project_id, entity_id, None, info], [paths]]


def active_media_workflow(records: list[dict[str, Any]], media_id: object) -> str:
    """Resolve a representative or measured batch member, never infer ownership."""
    if not is_uuid(media_id):
        raise ValueError("Source image must be an existing active project media UUID")
    workflows = {
        str(row["workflow_id"])
        for row in records
        if not row["archived"]
        and (row["media_id"] == media_id or media_id in row.get("batch_media_ids", []))
    }
    if len(workflows) != 1:
        raise ValueError("Source image must belong to one existing active project workflow")
    return workflows.pop()


async def _copy_image(
    page: Any, project_id: str, created_id: str, source_media_id: object, slot: int
) -> tuple[str, str]:
    if slot not in (0, 1):
        raise ValueError("Character copy supports portrait/body slots only")
    copied = await _rpc(
        page,
        project_id,
        "Sc7aEb",
        [
            source_media_id,
            None,
            None,
            project_id,
            None,
            None,
            None,
            [None, None, [created_id, [slot]]],
            None,
            str(uuid4()).upper(),
            str(uuid4()).upper(),
        ],
    )
    if not isinstance(copied, list) or len(cast("list[Any]", copied)) < 2:
        raise ValueError("Image binding reply has no media/workflow")
    media, workflow = cast("list[Any]", copied)[:2]
    if (
        not isinstance(media, list)
        or len(cast("list[Any]", media)) < 3
        or not isinstance(workflow, list)
        or len(cast("list[Any]", workflow)) < 6
        or media[1] != project_id
        or workflow[4] != project_id
        or workflow[5] != created_id
        or media[2] != workflow[0]
        or not is_uuid(cast("list[Any]", media)[0])
        or not is_uuid(cast("list[Any]", workflow)[0])
    ):
        raise ValueError("Image binding reply has unrelated identities")
    return str(cast("list[Any]", workflow)[0]), str(cast("list[Any]", media)[0])


async def mutate_character(
    page: Any,
    project_id: str,
    operation: str,
    entity_id: str = "",
    name: object = None,
    personality: object = None,
    workflow_id: object = None,
    image_reference_confirmed: bool = False,
    source_media_id: object = None,
    second_media_id: object = None,
) -> dict[str, Any]:
    payload = await read_project_payload(page, project_id)
    owned = parse_native_characters(payload, project_id)
    if operation != "create" and entity_id not in {row["entity_id"] for row in owned}:
        raise ValueError("Character must belong to the selected project")
    if operation == "create":
        # Validate the user name before the only mutation; creation has no generated portrait.
        if not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise ValueError("Character name must contain 1 to 200 characters")
        update_payload(project_id, project_id, name, personality)
        if not image_reference_confirmed:
            raise ValueError("Creation requires a caller-verified image reference")
        records = project_media(payload, project_id)
        if source_media_id is None:
            candidates = [
                row for row in records if row["workflow_id"] == workflow_id and not row["archived"]
            ]
            if len(candidates) != 1:
                raise ValueError("Creation requires an existing active project image workflow")
            source_media_id = candidates[0]["media_id"]
        resolved = active_media_workflow(records, source_media_id)
        if workflow_id is not None and workflow_id != resolved:
            raise ValueError("Source image must match the selected active workflow")
        sources = [source_media_id]
        if second_media_id is not None:
            active_media_workflow(records, second_media_id)
            sources.append(second_media_id)
        data = await _rpc(page, project_id, "C4BZMd", [[project_id, None, None, [1, name, []]]])
        created = parse_native_characters([None, [], [], [], None, data], project_id)
        if len(created) != 1:
            raise ValueError("Character creation was not acknowledged")
        created_id = str(created[0]["entity_id"])
        try:
            async with asyncio.timeout(POST_MUTATION_TIMEOUT):
                copied_refs: set[str] = set()
                for slot, source in enumerate(sources):
                    workflow, _ = await _copy_image(page, project_id, created_id, source, slot)
                    copied_refs.add(workflow)
                if len(copied_refs) != len(sources):
                    raise ValueError("Character image copies do not have distinct workflows")
                for attempt in range(6):
                    listed = parse_native_characters(
                        await read_project_payload(page, project_id), project_id
                    )
                    matches = [
                        row
                        for row in listed
                        if row["entity_id"] == created_id
                        and copied_refs <= set(row["workflow_ids"])
                    ]
                    if matches:
                        if personality is not None:
                            return await mutate_character(
                                page, project_id, "update", created_id, personality=personality
                            )
                        return {"character": matches[0]}
                    if attempt < 5:
                        await asyncio.sleep(1)
                raise ValueError("Character binding not visible in native project yet")
        except Exception as exc:
            raise CharacterBindingError(created_id) from exc
    elif operation == "update":
        args = update_payload(project_id, entity_id, name, personality)
        data = await _rpc(page, project_id, "rzMKMb", args)
    elif operation == "delete":
        try:
            async with asyncio.timeout(POST_MUTATION_TIMEOUT):
                await _rpc(page, project_id, "cz8Z4b", [None, None, project_id, [entity_id]])
                for attempt in range(6):
                    remaining = parse_native_characters(
                        await read_project_payload(page, project_id), project_id
                    )
                    if entity_id not in {row["entity_id"] for row in remaining}:
                        break
                    if attempt == 5:
                        raise ValueError(
                            "Character deletion not yet visible; inspect before retrying"
                        )
                    await asyncio.sleep(1)
        except Exception as exc:
            raise CharacterDeletionError(entity_id) from exc
        return {"deleted": [entity_id]}
    else:
        raise ValueError("Unsupported character metadata operation")
    rows = parse_native_characters([None, [], [], [], None, data], project_id)
    if len(rows) != 1 or (operation == "update" and rows[0]["entity_id"] != entity_id):
        raise ValueError("Character mutation acknowledgement has an unrelated identity")
    if name is not None and rows[0]["display_name"] != name:
        raise ValueError("Character name update was not acknowledged")
    if personality is not None and rows[0]["personality"] != personality:
        raise ValueError("Character personality update was not acknowledged")
    return {"character": rows[0]}
