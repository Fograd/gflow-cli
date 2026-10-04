"""Explicit native CAPTCHA providers, fallback only before Google submission."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from gflow_cli.api.native_captcha import native_captcha_provider, validate_native_captcha_token
from gflow_cli.api.recaptcha import discover_site_key
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.captcha import PROVIDERS, CaptchaStats, ProviderKeys, Solver, SolverError


@contextmanager
def native_provider_context(
    payload: dict[str, Any], project: str, action: str, *, root: Path
) -> Generator[None]:
    """Use one bounded configured order; never resubmit after Google refusal."""
    order = payload.get("captchaOrder")
    retry = payload.get("captchaRetry")
    if retry is not None and (type(retry) is not int or retry != 1):
        raise ValueError("Native provider CAPTCHA supports one pre-submission attempt")
    if order is not None:
        if not isinstance(order, str):
            raise ValueError("Invalid native CAPTCHA provider order")
        names = order.split(",")
        if (
            not names
            or any(name not in PROVIDERS for name in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("Invalid native CAPTCHA provider order")
    else:
        names = list(PROVIDERS)
    if order is None and retry is None:
        yield
        return
    chosen: str | None = None
    stats = CaptchaStats(root)

    async def mint(page: Any, mint_action: str) -> str:
        nonlocal chosen
        keys = ProviderKeys(Path.home() / ".config/homelab")
        configured = [(name, keys.get(name)) for name in names]
        configured = [(name, key) for name, key in configured if key]
        if not configured:
            raise SolverError("Requested native CAPTCHA providers are not configured")
        url = str(page.url)
        try:
            key = await asyncio.wait_for(discover_site_key(page), timeout=10)
        except Exception:
            raise SolverError("Fresh native CAPTCHA site key is unavailable") from None
        # Scope was validated by the API helper. Use the actual current page URL,
        # never a fabricated resource or queued/cached authenticated URL.
        if str(page.url) != url:
            raise SolverError("Native CAPTCHA page changed before provider solving")
        for name, secret in configured:
            if str(page.url) != url:
                raise SolverError("Native CAPTCHA page changed before provider solving")
            stats.record(name, "solveStarted")
            try:
                solution = await Solver().solve(name, secret, url, key, mint_action)
                token = validate_native_captcha_token(solution.token)
            except (SolverError, ConfigurationError):
                stats.record(name, "solveFailed")
                continue
            chosen = name
            stats.record(name, "solved")
            return token
        raise SolverError("Configured providers failed before native Google submission")

    def observe(phase: str) -> None:
        if chosen is not None:
            stats.record(chosen, phase)

    with native_captcha_provider(mint, project_id=project, action=action, observe=observe):
        yield
