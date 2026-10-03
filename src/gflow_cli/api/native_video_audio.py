"""Separate native audio UUIDs from measured system-preset resource forms."""

from __future__ import annotations

from typing import Any

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
