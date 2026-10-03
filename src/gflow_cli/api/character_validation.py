"""Pure cross-surface native character input validation, without browser/data I/O."""

from __future__ import annotations

from uuid import UUID

from gflow_cli.api.character import VOICES
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import ConfigurationError


def validate_character_identifiers(project_id: str, entity_id: str) -> None:
    if not is_uuid(project_id) or not is_uuid(entity_id):
        raise ConfigurationError(detail="Project and character identifiers must be UUIDs")


def validate_character_selector(
    project_id: str, entity_id: object = None, name: object = None
) -> None:
    if not is_uuid(project_id) or (entity_id is None) == (name is None):
        raise ConfigurationError(
            detail="Provide a project UUID and exactly one character id or name"
        )
    if entity_id is not None and not is_uuid(entity_id):
        raise ConfigurationError(detail="Character identifier must be a UUID")
    if name is not None and (not isinstance(name, str) or not 1 <= len(name) <= 200):
        raise ConfigurationError(detail="Character selector name requires 1 to 200 characters")


def _metadata(display_name: object, personality: object) -> None:
    if display_name is not None and (
        not isinstance(display_name, str) or not 1 <= len(display_name) <= 200
    ):
        raise ConfigurationError(detail="Character name requires 1 to 200 characters")
    if personality is not None and (not isinstance(personality, str) or len(personality) > 2000):
        raise ConfigurationError(detail="Personality requires at most 2000 characters")


def normalize_preset_voice(voice: object) -> str | None:
    if voice is None:
        return None
    if is_uuid(voice):
        return str(UUID(str(voice)))
    if isinstance(voice, str):
        known = {v.name.lower(): v.name for v in VOICES}
        normalized = known.get(voice.strip().lower())
        if normalized:
            return normalized
    raise ConfigurationError(
        detail="Voice requires a known system preset or saved audio UUID; clearing is unsupported"
    )


def validate_create_inputs(
    project_id: str,
    display_name: object,
    image_reference_1: str,
    image_reference_2: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
) -> None:
    normalize_preset_voice(voice)
    _metadata(display_name, personality)
    if display_name is None or not is_uuid(project_id) or not is_uuid(image_reference_1):
        raise ConfigurationError(
            detail="Creation requires a name, project UUID and image media UUID"
        )
    if image_reference_2 is not None and (
        not is_uuid(image_reference_2) or image_reference_2 == image_reference_1
    ):
        raise ConfigurationError(detail="Second reference must be a distinct image media UUID")


def validate_update_inputs(
    project_id: str,
    entity_id: str,
    display_name: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
) -> None:
    normalize_preset_voice(voice)
    validate_character_identifiers(project_id, entity_id)
    _metadata(display_name, personality)
    if display_name is None and personality is None and voice is None:
        raise ConfigurationError(
            detail="Update requires name, personality and/or a preset or saved voice"
        )
