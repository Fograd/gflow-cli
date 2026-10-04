"""Shared SDK bridge to measured native character metadata; no extra browser."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gflow_cli.api.character import Character
from gflow_cli.api.transports import migrated_characters, migrated_resources
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import CharacterMutationUnknownError, ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


def to_character(row: dict[str, Any]) -> Character:
    return Character(
        entity_id=row["entity_id"],
        display_name=row["display_name"],
        project_id=row["project_id"],
        workflow_ids=tuple(row["workflow_ids"]),
        voice=row.get("voice"),
        personality=row.get("personality"),
        thumbnail_media_id=row.get("thumbnail_media_id"),
    )


async def list_native(client: FlowApiClient, project_id: str) -> list[Character]:
    if not is_uuid(project_id):
        raise ConfigurationError(detail="Native project identifier must be a UUID")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        rows = parse_native_characters(
            await migrated_resources.read_project_payload(page, project_id), project_id
        )
        return [to_character(row) for row in rows]
    except ValueError as exc:
        raise WireFormatError(
            detail="Native character listing has an invalid shape", route="character.list"
        ) from exc
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def mutate_native(
    client: FlowApiClient, project_id: str, operation: str, entity_id: str = "", **kwargs: Any
) -> dict[str, Any]:
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native character mutations require the migrated Flow host")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        return await migrated_characters.mutate_character(
            page, project_id, operation, entity_id, **kwargs
        )
    except (
        migrated_characters.CharacterBindingError,
        migrated_characters.CharacterDeletionError,
        migrated_characters.CharacterCreationError,
        migrated_characters.CharacterUpdateError,
    ) as exc:
        raise CharacterMutationUnknownError(
            project_id=project_id, operation=operation, character_ref=exc.entity_id or None
        ) from exc
    except ValueError as exc:
        raise ConfigurationError(
            detail="Native character preflight refused the request", route="character." + operation
        ) from exc
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def detail_native(
    client: FlowApiClient,
    project_id: str,
    *,
    entity_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Explicit confidential detail; catalog Character models remain URL-free."""
    import asyncio

    from gflow_cli.api.registered_lookup import resolve_client_lookup, verify_resource
    from gflow_cli.api.transports.character_details import lookup_character
    from gflow_cli.selfhost.native_resource_aliases import NativeResourceAlias

    binding = None
    if entity_id is not None:
        binding = resolve_client_lookup(client, project_id, entity_id, "character")
        if isinstance(binding, NativeResourceAlias):
            entity_id = binding.native_id
    if not is_uuid(project_id) or (entity_id is not None and not is_uuid(entity_id)):
        raise ConfigurationError(detail="Native character/project identifiers must be UUIDs")
    if (entity_id is None) == (name is None):
        raise ConfigurationError(detail="Provide exactly one character ID or exact name")
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native character detail requires migrated Flow")
    try:
        async with asyncio.timeout(90):
            page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
            try:
                detail = await lookup_character(
                    page, project_id=project_id, entity_id=entity_id, name=name
                )
                verify_resource(binding, detail)
                return detail
            finally:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
    except (ValueError, TimeoutError):
        raise WireFormatError(
            detail="Native character detail is unresolved; inspect the selected project",
            route="character.detail",
        ) from None
