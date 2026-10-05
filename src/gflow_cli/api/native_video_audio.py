"""Separate native audio UUIDs from measured system-preset resource forms."""

from __future__ import annotations

from typing import Any, cast

from gflow_cli.api.character import VOICE_NAMES
from gflow_cli.api.transports.migrated_catalog import parse_native_voices
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError

_PRESETS = {name.lower(): name for name in VOICE_NAMES}


def normalize_audio_reference(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigurationError(detail="Video audio requires a UUID or recognized system preset")
    try:
        return validate_identifier(value)
    except ValueError:
        pass
    if value.startswith("voices/"):
        suffix = value[7:]
        canonical = _PRESETS.get(suffix) if suffix == suffix.lower() else None
    else:
        canonical = _PRESETS.get(value.lower()) if "/" not in value else None
    if canonical is None:
        raise ConfigurationError(detail="Video audio requires a UUID or recognized system preset")
    return canonical


def audio_wire_id(value: str) -> str:
    canonical = normalize_audio_reference(value)
    return canonical.lower() if canonical.lower() in _PRESETS else canonical


def validate_audio_presets(payload: Any, values: tuple[str, ...]) -> tuple[str, ...]:
    """Require unique current catalog matches; return UUIDs for caller ownership checks."""
    normalized = tuple(normalize_audio_reference(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError(
            detail="Video audio references must be distinct after normalization"
        )
    presets = tuple(value for value in normalized if value.lower() in _PRESETS)
    if presets:
        try:
            rows = parse_native_voices(payload)
            for preset in presets:
                if sum(row["voice"].lower() == preset.lower() for row in rows) != 1:
                    raise ValueError
        except (ValueError, TypeError, IndexError, KeyError):
            raise ConfigurationError(
                detail="Video system preset availability was not uniquely observed"
            ) from None
    return tuple(value for value in normalized if value.lower() not in _PRESETS)


def validate_owned_audio(
    payload: Any, project: str, audio_ids: tuple[str, ...], *, max_refs: int
) -> None:
    """Exclusive native audio joined to exactly one active owned workflow."""
    if not audio_ids:
        return
    try:
        project = validate_identifier(project)
        references = tuple(validate_identifier(value) for value in audio_ids)
        if len(references) > max_refs or len(set(references)) != len(references):
            raise ValueError
        if not isinstance(payload, list) or len(cast(list[Any], payload)) < 3:
            raise ValueError
        workflows, media = cast(list[Any], payload)[1:3]
        if not isinstance(workflows, list) or not isinstance(media, list):
            raise ValueError
        owned: dict[str, list[Any]] = {}
        for candidate in cast(list[Any], workflows):
            if (
                not isinstance(candidate, list)
                or len(cast(list[Any], candidate)) < 5
                or candidate[4] != project
            ):
                raise ValueError
            row = cast(list[Any], candidate)
            identifier = validate_identifier(row[0])
            if identifier in owned:
                raise ValueError
            owned[identifier] = row
        found: set[str] = set()
        seen: set[str] = set()
        for candidate in cast(list[Any], media):
            if (
                not isinstance(candidate, list)
                or len(cast(list[Any], candidate)) < 3
                or candidate[1] != project
            ):
                raise ValueError
            row = cast(list[Any], candidate)
            identifier, workflow = validate_identifier(row[0]), validate_identifier(row[2])
            if identifier in seen:
                raise ValueError
            seen.add(identifier)
            if identifier not in references:
                continue
            if len(row) <= 10 or row[6] is not None or row[7] is not None:
                raise ValueError
            audio = row[10]
            if (
                not isinstance(audio, list)
                or len(cast(list[Any], audio)) != 1
                or not isinstance(audio[0], list)
                or not audio[0]
            ):
                raise ValueError
            parent = owned.get(workflow)
            details = parent[3] if parent is not None else None
            if (
                not isinstance(details, list)
                or len(cast(list[Any], details)) < 5
                or details[2] not in (None, False, 0)
            ):
                raise ValueError
            validate_identifier(cast(list[Any], details)[4])
            found.add(identifier)
        if found != set(references):
            raise ValueError
    except (ValueError, TypeError, IndexError, ConfigurationError):
        raise ConfigurationError(
            detail="Video audio requires exclusive active owned native audio media"
        ) from None
