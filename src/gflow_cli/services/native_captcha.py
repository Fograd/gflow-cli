"""Public native provider controls; policy and solver implementation stay shared."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from gflow_cli.api.native_captcha import native_captcha_supplied_active
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.captcha import PROVIDERS, SolverError


def native_captcha_controls(
    *,
    captcha_order: object = None,
    captcha_retry: int | None = None,
    supplied_token: bool = False,
) -> dict[str, Any]:
    """Map explicit controls only; omission preserves the browser-owned one attempt."""
    if (supplied_token or native_captcha_supplied_active()) and (
        captcha_order is not None or captcha_retry is not None
    ):
        raise ConfigurationError(
            detail="A supplied CAPTCHA token cannot be combined with provider order or attempts"
        )
    if captcha_retry is not None and (
        type(captcha_retry) is not int or not 1 <= captcha_retry <= 10
    ):
        raise ConfigurationError(detail="CAPTCHA attempts require an integer from 1 through 10")
    if captcha_order is not None:
        names = captcha_order.split(",") if isinstance(captcha_order, str) else []
        if (
            not names
            or any(name not in PROVIDERS for name in names)
            or len(set(names)) != len(names)
        ):
            raise ConfigurationError(
                detail="CAPTCHA provider order requires unique CapSolver or 2Captcha names"
            )
    return {
        **({"captchaOrder": captcha_order} if captcha_order is not None else {}),
        **({"captchaRetry": captcha_retry} if captcha_retry is not None else {}),
    }


@contextmanager
def native_provider_errors(*, active: bool) -> Generator[None]:
    """Translate selected-provider setup/mint failure without exposing raw solver data."""
    try:
        yield
    except SolverError:
        if not active:
            raise
        raise ConfigurationError(
            detail="Configured native CAPTCHA providers could not supply a token",
            remediation_hint=(
                "Configure GFLOW_CAPSOLVER_KEY or GFLOW_2CAPTCHA_KEY in the existing private "
                "provider settings. Inspect the request state before trying again."
            ),
        ) from None
