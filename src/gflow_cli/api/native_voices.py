"""Portable saved-TTS operations using the native project transport."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Literal

from gflow_cli.api.registered_lookup import resolve_client_lookup, verify_resource
from gflow_cli.api.transports import native_voices as transport
from gflow_cli.errors import ConfigurationError, VoiceMutationUnknownError
from gflow_cli.selfhost.native_resource_aliases import NativeResourceAlias

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


def validate_create(project: str, name: str, preset: str, dialog: str, performance: str) -> None:
    try:
        transport.preview_payload(
            project,
            preset=preset,
            dialogue=dialog,
            performance=performance,
            display_name=name,
            captcha_token="validation-only",
        )
    except ValueError as error:
        raise ConfigurationError(detail=str(error)) from None


async def operate(
    client: FlowApiClient,
    operation: Literal["list", "get", "create", "delete"],
    project_id: str,
    *,
    voice_id: str | None = None,
    display_name: str = "",
    preset_voice: str = "",
    dialog: str = "",
    performance: str = "",
    confirm_delete: object = False,
) -> dict[str, Any]:
    binding = None
    if operation == "get" and voice_id is not None:
        binding = resolve_client_lookup(client, project_id, voice_id, "voice")
        if isinstance(binding, NativeResourceAlias):
            voice_id = binding.native_id
    try:
        project = transport.validate_identifier(project_id)  # pyright: ignore[reportPrivateUsage]
        if operation in {"get", "delete"}:
            voice_id = transport.validate_identifier(voice_id)  # pyright: ignore[reportPrivateUsage]
        if operation == "delete" and confirm_delete is not True:
            raise ValueError("Saved voice deletion requires explicit confirmation")
        if operation == "create":
            validate_create(project, display_name, preset_voice, dialog, performance)
    except ValueError as error:
        raise ConfigurationError(detail=str(error)) from None
    if client.settings.flow_host == "labs.google":
        raise ConfigurationError(detail="Saved TTS operations require the native Flow host")
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    outcome: dict[str, Any] = {}
    try:
        if operation == "list":
            outcome = await transport.list_saved_voices(page, project)
        elif operation == "get":
            assert voice_id is not None
            outcome = await transport.get_saved_voice(page, project, voice_id)
            verify_resource(binding, outcome)
        elif operation == "delete":
            assert voice_id is not None
            outcome = await transport.delete_saved_voice(page, project, voice_id, True)
        else:
            outcome = await transport.create_saved_voice(
                page, project, display_name, preset_voice, dialog, performance
            )
        return outcome
    finally:
        primary = sys.exc_info()[1]
        try:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
        except BaseException:
            if primary is not None:
                primary.add_note("Saved voice browser checkin remains incomplete")
            elif operation in {"create", "delete"} and outcome:
                raise VoiceMutationUnknownError(
                    project_id=project,
                    phase="save" if operation == "create" else "delete",
                    media_id=outcome.get("ref", voice_id),
                    workflow_id=outcome.get("workflow_id"),
                ) from None
            else:
                raise
