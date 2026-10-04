"""Generic image adapters around the existing ImageOverrides policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from gflow_cli.api.transports.migrated_image_overrides import active_overrides
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.captcha import SolverError
from gflow_cli.selfhost.config import environment_root
from gflow_cli.selfhost.image_captcha_policy import (
    run_with_image_captcha_policy,
    validate_image_captcha_controls,
)


async def generate_images_with_captcha(
    client: Any,
    *,
    req: Any,
    project_id: str,
    captcha_order: str | None = None,
    captcha_retry: int | None = None,
    root: Path | None = None,
    **kwargs: Any,
) -> list[Any]:
    """Retry generation only after the image override's exact negative acknowledgment."""
    payload = {
        "count": req.count,
        **({"seed": req.seed} if req.seed is not None else {}),
        **({"captchaOrder": captcha_order} if captcha_order is not None else {}),
        **({"captchaRetry": captcha_retry} if captcha_retry is not None else {}),
    }
    try:
        selected = validate_image_captcha_controls(payload, project_id)
    except ValueError as error:
        raise ConfigurationError(detail=str(error)) from None

    async def attempt(override: Any = None) -> list[Any]:
        if req.count == 1:
            return [await client.generate_image(req=req, project_id=project_id, **kwargs)]
        return await client.generate_images_batch(
            req=req, project_id=project_id, count=req.count, **kwargs
        )

    if not selected:
        return await attempt()
    if active_overrides.get() is not None:
        raise ConfigurationError(
            detail="Explicit image providers cannot replace an active image scope"
        )
    require_native_image_captcha_host(client)
    try:
        images, _ = await run_with_image_captcha_policy(
            payload, project_id, root or environment_root(), attempt
        )
    except SolverError:
        raise ConfigurationError(
            detail="Configured image CAPTCHA providers could not supply a token",
            remediation_hint=(
                "Configure GFLOW_CAPSOLVER_KEY or GFLOW_2CAPTCHA_KEY in the existing private "
                "provider settings. Inspect request state before trying again."
            ),
        ) from None
    return images


def require_native_image_captcha_host(client: Any) -> None:
    """Explicit provider controls must never fall through to an unguarded legacy submit."""
    try:
        observed = urlsplit(str(getattr(getattr(client, "_page", None), "url", "")))
        native = observed.scheme == "https" and observed.netloc == "flow.google.com"
    except ValueError:
        native = False
    if not native or getattr(getattr(client, "transport", None), "name", None) != "ui_automation":
        raise ConfigurationError(
            detail="Explicit image CAPTCHA requires a loaded native flow.google.com UI session"
        )
