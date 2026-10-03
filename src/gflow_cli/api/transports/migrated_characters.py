"""Measured native character metadata operations; no portrait or voice generation."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID, uuid4

from gflow_cli.api.character import VOICE_NAMES
from gflow_cli.api.transports.migrated_catalog import parse_native_characters, parse_native_voices
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.api.transports.native_voices import get_saved_voice

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


class CharacterCreationError(ValueError):
    """Create was sent but acknowledgement is uncertain; never create again blindly."""

    entity_id = ""


class CharacterUpdateError(ValueError):
    """Metadata update may have applied; retain the known character identifier."""

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        super().__init__("Character update outcome unknown; inspect before retrying")


async def _rpc(page: Any, project_id: str, rpc: str, args: list[Any]) -> Any:
    return await native_rpc(page, rpc, args, "/project/" + project_id)


def update_payload(
    project_id: str,
    entity_id: str,
    name: object = None,
    personality: object = None,
    voice: object = None,
) -> list[Any]:
    if not is_uuid(project_id) or not is_uuid(entity_id):
        raise ValueError("Character identifiers must be UUIDs")
    if name is None and personality is None and voice is None:
        raise ValueError("At least one character metadata field is required")
    if name is not None and (not isinstance(name, str) or not 1 <= len(name) <= 200):
        raise ValueError("Character name must contain 1 to 200 characters")
    if personality is not None and (not isinstance(personality, str) or len(personality) > 4000):
        raise ValueError("Personality must be a string of at most 4000 characters")
    if voice is not None:
        voice = normalize_voice(voice)
    paths: list[str] = []
    if name is not None:
        paths.append("entity_info.display_name")
    if personality is not None:
        paths.append("entity_info.character_info.personality_notes")
    info: list[Any] = [1, name]
    if voice is not None:
        paths.append("entity_info.character_info.audio_references")
    if personality is not None or voice is not None:
        character_info: list[Any] = [
            None,
            ([[str(voice)]] if is_uuid(voice) else [[None, str(voice).lower()]]) if voice else None,
        ]
        if personality is not None:
            character_info.append(personality)
        info.append(character_info)
    return [[project_id, entity_id, None, info], [paths]]


def normalize_voice(value: object) -> str:
    if is_uuid(value):
        return str(UUID(str(value)))
    if not isinstance(value, str):
        raise ValueError("Voice must be a system preset name; clearing is unverified")
    canonical = next((name for name in VOICE_NAMES if name.lower() == value.lower()), None)
    if canonical is None:
        raise ValueError("Voice must be a known system preset; clearing is unverified")
    return canonical


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
    voice: object = None,
) -> dict[str, Any]:
    if voice is not None:
        voice = normalize_voice(voice)
    if operation in {"create", "update"}:
        update_payload(
            project_id, project_id if operation == "create" else entity_id, name, personality, voice
        )
    payload = await read_project_payload(page, project_id)
    if voice is not None:
        if is_uuid(voice):
            # Fresh selected-project catalog plus GetMedia exclusive audio proof, before mutation.
            await get_saved_voice(page, project_id, voice)
        elif voice not in {row["voice"] for row in parse_native_voices(payload)}:
            raise ValueError("Voice is not present in the current native system preset catalog")
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
        try:
            data = await _rpc(page, project_id, "C4BZMd", [[project_id, None, None, [1, name, []]]])
            created = parse_native_characters([None, [], [], [], None, data], project_id)
            if len(created) != 1:
                raise ValueError("Character creation was not acknowledged")
        except Exception as exc:
            raise CharacterCreationError(
                "Creation outcome unknown; inspect before retrying"
            ) from exc
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
                        if personality is not None or voice is not None:
                            return await mutate_character(
                                page,
                                project_id,
                                "update",
                                created_id,
                                personality=personality,
                                voice=voice,
                            )
                        return {"character": matches[0]}
                    if attempt < 5:
                        await asyncio.sleep(1)
                raise ValueError("Character binding not visible in native project yet")
        except Exception as exc:
            raise CharacterBindingError(created_id) from exc
    elif operation == "update":
        args = update_payload(project_id, entity_id, name, personality, voice)
        try:
            async with asyncio.timeout(POST_MUTATION_TIMEOUT):
                data = await _rpc(page, project_id, "rzMKMb", args)
                return await _ack_update(
                    page, project_id, entity_id, data, name, personality, voice
                )
        except Exception as exc:
            raise CharacterUpdateError(entity_id) from exc
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


async def _ack_update(
    page: Any,
    project_id: str,
    entity_id: str,
    data: Any,
    name: object,
    personality: object,
    voice: object,
) -> dict[str, Any]:
    try:
        rows = parse_native_characters([None, [], [], [], None, data], project_id)
        if len(rows) != 1 or rows[0]["entity_id"] != entity_id:
            raise ValueError("Character mutation acknowledgement has an unrelated identity")
        if name is not None and rows[0]["display_name"] != name:
            raise ValueError("Character name update was not acknowledged")
        if personality is not None and (rows[0]["personality"] or "") != personality:
            raise ValueError("Character personality update was not acknowledged")
        if voice is not None and rows[0]["voice"] != voice:
            raise ValueError("Character preset assignment was not acknowledged")
        if voice is not None or personality == "":
            consecutive = 0
            for attempt in range(6):
                fresh = parse_native_characters(
                    await read_project_payload(page, project_id), project_id
                )
                matches = [
                    row
                    for row in fresh
                    if row["entity_id"] == entity_id
                    and (voice is None or row["voice"] == voice)
                    and (personality != "" or (row["personality"] or "") == "")
                ]
                consecutive = consecutive + 1 if matches else 0
                if matches and consecutive >= (2 if personality == "" else 1):
                    return {"character": matches[0]}
                if attempt < 5:
                    await asyncio.sleep(1)
            raise ValueError("Character metadata update not yet visible")
        return {"character": rows[0]}
    except Exception as exc:
        raise CharacterUpdateError(entity_id) from exc
