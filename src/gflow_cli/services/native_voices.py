"""Shared direct saved-TTS service for public adapters."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_captcha import native_captcha_or_none
from gflow_cli.api.native_voices import operate
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError, VoiceMutationUnknownError, WafRejectionError
from gflow_cli.selfhost.native_captcha_policy import run_with_native_captcha_policy
from gflow_cli.services.native_captcha import native_captcha_controls, native_provider_errors


async def saved_voice_operation(
    *,
    profile: str,
    operation: Literal["list", "get", "create", "delete"],
    project_id: str,
    captcha_order: str | None = None,
    captcha_retry: int | None = None,
    captcha_token: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a fresh client per exact WAF refusal; never replay accepted or unknown speech."""
    if operation == "get":
        from gflow_cli.api.registered_lookup import resolve_lookup

        resolve_lookup(profile, project_id, kwargs["voice_id"], "voice")
    controls = native_captcha_controls(
        captcha_order=captcha_order,
        captcha_retry=captcha_retry,
        supplied_token=captcha_token is not None,
    )
    if operation != "create" and (controls or captcha_token is not None):
        raise ConfigurationError(detail="CAPTCHA controls apply only to saved voice creation")

    async def attempt() -> dict[str, Any]:
        return await _saved_voice_attempt(
            profile=profile,
            operation=operation,
            project_id=project_id,
            stop_on_teardown_failure=bool(controls),
            **kwargs,
        )

    with (
        native_provider_errors(active=bool(controls)),
        native_captcha_or_none(captcha_token, project_id=project_id, action="AUDIO_GENERATION"),
    ):
        if operation != "create":
            return await attempt()
        return await run_with_native_captcha_policy(
            controls, project_id, "AUDIO_GENERATION", attempt
        )


async def _saved_voice_attempt(
    *,
    profile: str,
    operation: Literal["list", "get", "create", "delete"],
    project_id: str,
    stop_on_teardown_failure: bool = False,
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
            if (
                stop_on_teardown_failure
                and error is not primary
                and isinstance(primary, WafRejectionError)
            ):
                if isinstance(error, asyncio.CancelledError):
                    raise error
                raise ConfigurationError(
                    detail="Saved voice browser teardown did not complete; no retry was attempted"
                ) from None
            raise primary from None
        if operation in {"create", "delete"} and outcome:
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
