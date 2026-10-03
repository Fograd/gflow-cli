"""Shared direct saved-TTS service for public adapters."""

from __future__ import annotations

from typing import Any, Literal

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_voices import operate
from gflow_cli.config import get_settings
from gflow_cli.errors import VoiceMutationUnknownError


async def saved_voice_operation(
    *,
    profile: str,
    operation: Literal["list", "get", "create", "delete"],
    project_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    settings = get_settings()
    primary: BaseException | None = None
    outcome: dict[str, Any] = {}
    try:
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(profile), headless=settings.headless
        ) as client:
            try:
                outcome = await operate(client, operation, project_id, **kwargs)
            except BaseException as error:
                primary = error
                raise
    except BaseException as error:
        if primary is not None:
            raise primary from None
        if operation in {"create", "delete"} and outcome:
            import asyncio

            typed = VoiceMutationUnknownError(
                project_id=project_id,
                phase="save" if operation == "create" else "delete",
                media_id=outcome.get("ref", kwargs.get("voice_id")),
                workflow_id=outcome.get("workflow_id"),
            )
            if isinstance(error, asyncio.CancelledError):
                vars(error)["gflow_saved_voice_unknown"] = typed
                raise
            raise typed from None
        raise
    return outcome
