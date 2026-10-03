"""Fresh character video references and source-defined capacity pools."""

from __future__ import annotations

from typing import Any, cast

from gflow_cli.api.character import VOICE_NAMES
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_video_edit import validate_edit_audio
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_resources import project_media
from gflow_cli.api.transports.native_voices import validate_identifier as _uuid
from gflow_cli.errors import ConfigurationError


def character_reference_counts(
    payload: Any, project: str, entities: tuple[str, ...]
) -> dict[str, tuple[int, int]]:
    """Positive projected images and strict linked audio; no saved-visibility requirement."""
    if not entities:
        return {}
    try:
        project = _uuid(project)
        selected = tuple(_uuid(value) for value in entities)
        if len(selected) > 7 or len(set(selected)) != len(selected):
            raise ValueError
        characters = parse_native_characters(payload, project)
        owned = {_uuid(row["entity_id"]): row for row in characters}
        if len(owned) != len(characters):
            raise ValueError
        media = parse_media_snapshot(payload, project)["media"]
        typed = {_uuid(row["media_id"]): row for row in media}
        timeline = project_media(payload, project)
        workflows = {_uuid(row["workflow_id"]): row for row in timeline}
        if len(workflows) != len(timeline):
            raise ValueError
        raw_workflows = {_uuid(row[0]): row for row in payload[1]}
        if len(raw_workflows) != len(payload[1]):
            raise ValueError
        raw_rows: list[Any] = payload[5] if payload[5] is not None else []
        raw_entities = {_uuid(row[1]): row for row in raw_rows}
        if len(raw_entities) != len(raw_rows):
            raise ValueError
        result: dict[str, tuple[int, int]] = {}
        for entity in selected:
            character = owned.get(entity)
            if character is None:
                raise ValueError
            raw = raw_entities[entity]
            if raw[3][0] != 1:
                raise ValueError
            info = raw[3][2]
            refs = info[0]
            if not isinstance(refs, list) or not 1 <= len(cast(list[Any], refs)) <= 7:
                raise ValueError
            ids: list[str] = []
            for ref in cast(list[Any], refs):
                if not isinstance(ref, list) or len(cast(list[Any], ref)) != 1:
                    raise ValueError
                workflow = _uuid(cast(list[Any], ref)[0])
                ids.append(workflow)
                row = workflows.get(workflow)
                parent = raw_workflows.get(workflow)
                if (
                    row is None
                    or row["archived"]
                    or parent is None
                    or len(parent) < 6
                    or parent[5] != entity
                ):
                    raise ValueError
                linked = [value for value in typed.values() if value["workflow_id"] == workflow]
                if not linked or any(
                    value["kind"] != "image"
                    or type(value.get("width")) is not int
                    or type(value.get("height")) is not int
                    for value in linked
                ):
                    raise ValueError
                for value in linked:
                    record = next(item for item in payload[2] if item[0] == value["media_id"])
                    if len(record) > 10 and record[10] is not None:
                        raise ValueError
            if len(ids) != len(set(ids)):
                raise ValueError
            audio = info[1] if len(info) > 1 else None
            count = 0
            if audio is not None:
                if not isinstance(audio, list) or len(cast(list[Any], audio)) > 5:
                    raise ValueError
                for reference in cast(list[Any], audio):
                    if not isinstance(reference, list):
                        raise ValueError
                    reference = cast(list[Any], reference)
                    if len(reference) == 1:
                        validate_edit_audio(payload, project, (_uuid(reference[0]),))
                    elif (
                        len(reference) == 2
                        and reference[0] is None
                        and isinstance(reference[1], str)
                        and reference[1] in {name.lower() for name in VOICE_NAMES}
                    ):
                        pass
                    else:
                        raise ValueError
                    count += 1
            result[entity] = (len(ids), count)
        return result
    except (ValueError, TypeError, IndexError, KeyError, StopIteration, ConfigurationError):
        raise ConfigurationError(
            detail="Video characters require fresh exclusive active owned image/audio links"
        ) from None


def reference_capacity(
    images: int, audio: int, characters: dict[str, tuple[int, int]], limits: tuple[Any, Any, Any]
) -> bool:
    """Frontend field22: audio1, character2, image3; linked audio applies when cap>0."""
    audio_cap, char_cap, image_cap = limits
    if (
        type(image_cap) is not int
        or image_cap < 0
        or images + sum(v[0] for v in characters.values()) > image_cap
    ):
        return False
    if characters and (type(char_cap) is not int or char_cap < 0 or len(characters) > char_cap):
        return False
    if audio or characters:
        if type(audio_cap) is not int or audio_cap < 0:
            return False
        if audio > audio_cap or (
            audio_cap > 0 and audio + sum(v[1] for v in characters.values()) > audio_cap
        ):
            return False
    return True


def classify_video_slots(payload: Any, project: str, slot_ids: dict[str, str]) -> dict[str, Any]:
    """Preserve body positions; classify fresh owned namespaces without substitutions."""
    from gflow_cli.api.reference_markers import ReferenceSlot

    try:
        characters = parse_native_characters(payload, project)
        raw_rows: list[Any] = payload[5] if payload[5] is not None else []
        raw_entities = {_uuid(row[1]): row for row in raw_rows}
        if len(raw_entities) != len(raw_rows):
            raise ValueError
        owned = {_uuid(row["entity_id"]) for row in characters}
        media = {_uuid(row[0]) for row in payload[2]}
        slots: dict[str, Any] = {}
        for key, value in slot_ids.items():
            value = _uuid(value)
            if value in owned & media:
                raise ValueError
            kind = (
                "audio"
                if key.startswith("referenceAudio_")
                else "character"
                if key.startswith("character_") or value in owned
                else "image"
            )
            slots[key] = ReferenceSlot(kind, value)
        return slots
    except (ValueError, TypeError, IndexError, KeyError):
        raise ConfigurationError(
            detail="Native video slot identity or ownership is ambiguous"
        ) from None


def model_reference_limits(payload: Any, key: str) -> tuple[Any, Any, Any]:
    """Native usage field22 pools: audio1, character2, image3; unknown stays unknown."""
    from gflow_cli.api.transports.batchexecute import _at  # pyright: ignore[reportPrivateUsage]

    values: list[tuple[Any, Any, Any]] = []
    families = _at(payload, 0, 4)
    if isinstance(families, list):
        for family in cast(list[Any], families):
            usages = _at(family, 1)
            if not isinstance(usages, list):
                continue
            for usage in cast(list[Any], usages):
                if _at(usage, 0) == key:
                    values.append((_at(usage, 21, 0), _at(usage, 21, 1), _at(usage, 21, 2)))
    if len(values) != 1:
        raise ConfigurationError(
            detail="Native reference model capacities were not uniquely observed"
        )
    return values[0]
