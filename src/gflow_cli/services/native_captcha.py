"""Public native provider controls; policy and solver implementation stay shared."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, TypeVar
from urllib.parse import urlsplit

from gflow_cli.api.native_captcha import native_captcha_or_none, native_captcha_supplied_active
from gflow_cli.errors import ConfigurationError, WafRejectionError
from gflow_cli.selfhost.captcha import PROVIDERS, SolverError
from gflow_cli.selfhost.native_captcha_policy import run_with_native_captcha_policy


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


_Result = TypeVar("_Result")


async def run_native_captcha_with_controls(
    *,
    project_id: str,
    action: str,
    attempt: Callable[[], Awaitable[_Result]],
    captcha_order: str | None = None,
    captcha_retry: int | None = None,
    captcha_token: str | None = None,
) -> _Result:
    """Run complete fresh-client callbacks with the existing exact-refusal policy."""
    controls = native_captcha_controls(
        captcha_order=captcha_order,
        captcha_retry=captcha_retry,
        supplied_token=captcha_token is not None,
    )
    with (
        native_provider_errors(active=bool(controls)),
        native_captcha_or_none(captcha_token, project_id=project_id, action=action),
    ):
        return await run_with_native_captcha_policy(controls, project_id, action, attempt)


def require_native_captcha_client(client: Any, *, active: bool) -> None:
    """Selected image providers require an actually loaded native host before mint."""
    if not active:
        return
    page_url = str(getattr(getattr(client, "_page", None), "url", ""))
    try:
        native = urlsplit(page_url).hostname == "flow.google.com"
    except ValueError:
        native = False
    if not native:
        raise ConfigurationError(
            detail="Explicit image CAPTCHA providers require a loaded flow.google.com session"
        )


@asynccontextmanager
async def native_captcha_client(client: Any, *, active: bool) -> AsyncGenerator[Any]:
    """Do not replay a refusal when selected-provider client teardown also fails."""
    if not active:
        async with client as opened:
            yield opened
        return
    primary: BaseException | None = None
    try:
        async with client as opened:
            try:
                yield opened
            except BaseException as error:
                primary = error
                raise
    except BaseException as error:
        if primary is not None:
            if error is not primary and isinstance(primary, WafRejectionError):
                if isinstance(error, asyncio.CancelledError):
                    raise error
                raise ConfigurationError(
                    detail="Native browser teardown did not complete; no retry was attempted"
                ) from None
            raise primary from None
        raise
