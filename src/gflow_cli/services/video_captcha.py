"""Explicit SDK bridge for native UI video CAPTCHA controls.

Ordinary generate_video calls retain their browser behavior. Configured provider
keys live in the operator's existing private settings; no keys belong in DTOs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.captcha import SolverError
from gflow_cli.selfhost.config import environment_root
from gflow_cli.selfhost.video_captcha_policy import (
    run_with_video_captcha_policy,
    validate_video_captcha_controls,
)


async def generate_video_with_captcha(
    client: Any,
    *,
    req: Any,
    project_id: str,
    captcha_order: str | None = None,
    captcha_retry: int | None = None,
    captcha_token: str | None = None,
    root: Path | None = None,
    **kwargs: Any,
) -> Any:
    """Generate one current UI RPC; replay only an exact negative WAF acknowledgment."""
    payload = {
        "count": req.count,
        **({"captchaOrder": captcha_order} if captcha_order is not None else {}),
        **({"captchaRetry": captcha_retry} if captcha_retry is not None else {}),
        **({"captcha_token": captcha_token} if captcha_token is not None else {}),
    }
    try:
        validate_video_captcha_controls(payload, project_id)
    except ValueError as error:
        raise ConfigurationError(detail=str(error)) from None

    async def attempt(override: Any) -> Any:
        require_native_video_captcha_host(client, active=override is not None)
        if req.count > 1:
            batch_kwargs = {key: value for key, value in kwargs.items() if key != "name_resolver"}
            return await client.generate_videos_batch(
                req=req, project_id=project_id, **batch_kwargs
            )
        return await client.generate_video(req=req, project_id=project_id, **kwargs)

    try:
        value, _ = await run_with_video_captcha_policy(
            payload, project_id, root or environment_root(), attempt
        )
    except SolverError:
        raise ConfigurationError(
            detail="Video CAPTCHA providers are not configured or could not supply a token",
            remediation_hint=(
                "Configure GFLOW_CAPSOLVER_KEY or GFLOW_2CAPTCHA_KEY in the existing private "
                "provider settings. Inspect request state before trying again."
            ),
        ) from None
    return value


def require_native_video_captcha_host(client: Any, *, active: bool) -> None:
    """Refuse explicit controls before an unguarded legacy browser can submit."""
    if not active:
        return
    native = getattr(client, "_uses_native_characters", None)
    if callable(native) and not native():
        raise ConfigurationError(detail="Explicit video CAPTCHA requires native flow.google.com")
