"""Fresh image provider scopes; retries require exact negatively acknowledged dispatch."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from gflow_cli.api.native_captcha import read_native_token_file, validate_native_captcha_token
from gflow_cli.api.recaptcha import discover_site_key
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.errors import ConfigurationError, WafRejectionError
from gflow_cli.selfhost.captcha import PROVIDERS, CaptchaStats, ProviderKeys, Solver, SolverError
from gflow_cli.selfhost.native_captcha import native_secret_path

_Result = TypeVar("_Result")


async def run_with_image_captcha_policy(
    payload: dict[str, Any],
    project: str,
    root: Path,
    attempt: Callable[[ImageOverrides], Awaitable[_Result]],
) -> tuple[_Result, str | None]:
    budget = payload.get("captchaRetry", 1)
    if type(budget) is not int or not 1 <= budget <= 10:
        raise ValueError("Image CAPTCHA attempts require an integer from 1 through 10")
    order = payload.get("captchaOrder")
    names = list(PROVIDERS) if order is None else order.split(",") if isinstance(order, str) else []
    if not names or any(name not in PROVIDERS for name in names) or len(set(names)) != len(names):
        raise ValueError("Invalid image CAPTCHA provider order")
    selected = order is not None or payload.get("captchaRetry") is not None
    path = native_secret_path(payload, root)
    supplied = None
    if path is not None:
        try:
            supplied = read_native_token_file(path)
        finally:
            path.unlink(missing_ok=True)
        budget = 1
    if not selected:
        budget = 1
    stats = CaptchaStats(root)
    for index in range(budget):
        selection: dict[str, str | None] = {"chosen": None}
        override = ImageOverrides(
            project,
            payload["count"],
            seed=payload.get("seed"),
            metadata_required=selected and supplied is None,
        )

        async def mint(
            page: Any,
            override: ImageOverrides = override,
            selection: dict[str, str | None] = selection,
        ) -> str:
            nonlocal supplied
            if override.closed or not override.page_matches(page):
                raise SolverError("Image CAPTCHA scope is closed or mismatched")
            if supplied is not None:
                value, supplied = supplied, None
                selection["chosen"] = "supplied"
                return value
            metadata = override.metadata
            url = str(page.url)
            if (
                not override.page_matches(page)
                or metadata is None
                or override.metadata_url != url
                or not 0 <= time.monotonic() - override.metadata_at <= 120
                or metadata.get("action") != "IMAGE_GENERATION"
            ):
                raise SolverError("Fresh image CAPTCHA metadata is unavailable")
            key = await asyncio.wait_for(discover_site_key(page), timeout=10)
            if key != metadata.get("sitekey") or str(page.url) != url:
                raise SolverError("Current image CAPTCHA metadata does not match trusted page")
            keys = ProviderKeys(Path.home() / ".config/homelab")
            for name in names:
                secret = keys.get(name)
                if not secret:
                    continue
                if str(page.url) != url or not override.page_matches(page) or override.closed:
                    raise SolverError("Image CAPTCHA page changed before solving")
                stats.record(name, "solveStarted")
                try:
                    solution = await asyncio.wait_for(
                        Solver().solve(name, secret, url, key, "IMAGE_GENERATION"), timeout=120
                    )
                    value = validate_native_captcha_token(solution.token)
                except (SolverError, ConfigurationError, TimeoutError):
                    if override.closed:
                        raise SolverError("Image CAPTCHA scope closed during solving") from None
                    stats.record(name, "solveFailed")
                    continue
                if str(page.url) != url or override.closed:
                    raise SolverError("Image CAPTCHA scope changed during solving")
                selection["chosen"] = name
                stats.record(name, "solved")
                return value
            raise SolverError("Configured image providers failed before Google submission")

        def observe(phase: str, selection: dict[str, str | None] = selection) -> None:
            chosen = selection["chosen"]
            if chosen is not None:
                stats.record(chosen, phase)

        override.token = mint if selected or supplied is not None else None
        override.observe = observe
        handle = active_overrides.set(override)
        try:
            return await attempt(override), selection["chosen"]
        except WafRejectionError:
            if (
                path is not None
                or index + 1 >= budget
                or not override.submitted
                or override.terminal != "rejected"
            ):
                raise
        finally:
            override.close()
            active_overrides.reset(handle)
    raise AssertionError("Image CAPTCHA policy exhausted without a result")
