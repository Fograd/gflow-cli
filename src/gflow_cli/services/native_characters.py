"""Portable native character services shared by CLI/MCP; no REST registry."""

from __future__ import annotations

import asyncio

from PIL import Image

from gflow_cli.api.character import Character
from gflow_cli.api.character_validation import (
    normalize_preset_voice as normalize_preset_voice,
)
from gflow_cli.api.character_validation import (
    validate_character_identifiers as validate_character_identifiers,
)
from gflow_cli.api.character_validation import (
    validate_character_selector as validate_character_selector,
)
from gflow_cli.api.character_validation import (
    validate_create_inputs as validate_create_inputs,
)
from gflow_cli.api.character_validation import (
    validate_update_inputs as validate_update_inputs,
)
from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings
from gflow_cli.data.models import AssetKind
from gflow_cli.data.repository import DataRepository, verified_local_path
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError


def _verify_references(profile: str, project_id: str, ids: list[str]) -> None:
    with DataStore.open(get_settings().resolved_db_path()) as store:
        repo = DataRepository(store)
        assets = [repo.get_asset_by_flow_media_id(profile, mid) for mid in ids]
    for asset in assets:
        if (
            asset is None
            or asset.kind is not AssetKind.IMAGE
            or asset.flow_project_id != project_id
        ):
            raise ConfigurationError(
                detail="Every reference must be a catalogued image in the selected profile/project"
            )
        valid = False
        for local in asset.local_files:
            try:
                if local.path is None or local.path.stat().st_size > 20 * 1024 * 1024:
                    continue
                path = verified_local_path(local)
                if path is None:
                    continue
                with Image.open(path) as image:
                    if image.format not in ("JPEG", "PNG"):
                        continue
                    image.verify()
                # Header verification alone can accept truncated JPEG pixel data.
                with Image.open(path) as image:
                    image.load()
                valid = True
                break
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
        if not valid:
            raise ConfigurationError(
                detail="Every reference needs an integrity-verified local PNG/JPEG catalog copy"
            )


async def create_character_from_images(
    *,
    profile: str,
    project_id: str,
    display_name: str,
    image_reference_1: str,
    image_reference_2: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
) -> Character:
    validate_create_inputs(
        project_id, display_name, image_reference_1, image_reference_2, personality, voice
    )
    ids = [image_reference_1] + ([image_reference_2] if image_reference_2 else [])
    await asyncio.to_thread(_verify_references, profile, project_id, ids)
    settings = get_settings()
    async with FlowApiClient(
        profile_dir=settings.profile_subdir(profile), headless=settings.headless
    ) as client:
        return await client.create_character_from_images(
            project_id=project_id,
            display_name=display_name,
            media_id=image_reference_1,
            second_media_id=image_reference_2,
            personality=personality,
            image_reference_confirmed=True,
            voice=normalize_preset_voice(voice),
        )


async def update_character(
    *,
    profile: str,
    project_id: str,
    entity_id: str,
    display_name: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
) -> Character:
    validate_update_inputs(project_id, entity_id, display_name, personality, voice)
    settings = get_settings()
    async with FlowApiClient(
        profile_dir=settings.profile_subdir(profile), headless=settings.headless
    ) as client:
        return await client.update_character(
            project_id=project_id,
            entity_id=entity_id,
            display_name=display_name,
            personality=personality,
            voice=normalize_preset_voice(voice),
        )
