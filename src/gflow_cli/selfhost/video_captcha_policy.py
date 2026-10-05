"""Explicit one-RPC generic video providers and proven WAF-only retries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from gflow_cli.api.native_captcha import (
    native_captcha_supplied_active,
    read_native_token_file,
    validate_native_captcha_token,
)
from gflow_cli.api.recaptcha import discover_site_key
from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides, active_video_overrides
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError, WafRejectionError
from gflow_cli.selfhost.captcha import (
    PROVIDERS,
    CaptchaStats,
    ProviderKeys,
    Solver,
    SolverError,
    configured_provider_keys,
)
from gflow_cli.selfhost.native_captcha import native_secret_path

_Result = TypeVar("_Result")


def validate_video_captcha_controls(
    payload: dict[str, Any], project: str | None, *, queued: bool = False
) -> bool:
    selected = any(
        payload.get(key) is not None
        for key in (
            "captchaOrder",
            "captchaRetry",
            "captchaSecret",
            "captcha_token",
            "captcha_token_file",
            "captchaToken",
        )
    )
    if not selected:
        return False
    provider = any(payload.get(key) is not None for key in ("captchaOrder", "captchaRetry"))
    supplied = native_captcha_supplied_active() or any(
        payload.get(key) is not None
        for key in ("captcha_token", "captchaSecret", "captcha_token_file", "captchaToken")
    )
    if provider and supplied:
        raise ValueError("Supplied video tokens cannot be combined with provider controls")
    if queued and any(
        payload.get(key) is not None
        for key in ("captcha_token", "captchaSecret", "captcha_token_file", "captchaToken")
    ):
        raise ValueError("Confidential video tokens cannot enter the durable generation queue")
    if any(payload.get(key) is not None for key in ("captcha_token_file", "captchaToken")):
        raise ValueError("Video tokens require the supported private token input")
    if type(payload.get("count", 1)) is not int or not 1 <= payload.get("count", 1) <= 4:
        raise ValueError("Explicit generic video CAPTCHA requires one through four outputs")
    if project is None:
        raise ValueError("Explicit video CAPTCHA requires a selected project UUID")
    validate_identifier(project)
    retry = payload.get("captchaRetry", 1)
    if type(retry) is not int or not 1 <= retry <= 10:
        raise ValueError("Video CAPTCHA attempts require an integer from 1 through 10")
    order = payload.get("captchaOrder")
    if order is not None:
        names = order.split(",") if isinstance(order, str) else []
        if (
            not names
            or any(name not in PROVIDERS for name in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("Invalid video CAPTCHA provider order")
    if payload.get("captcha_token") is not None:
        validate_native_captcha_token(payload["captcha_token"])
    return True


async def run_with_video_captcha_policy(
    payload: dict[str, Any],
    project: str,
    root: Path,
    attempt: Callable[[VideoOverrides | None], Awaitable[_Result]],
) -> tuple[_Result, str | None]:
    if not validate_video_captcha_controls(payload, project):
        return await attempt(None), None
    budget = payload.get("captchaRetry", 1)
    names = (
        list(PROVIDERS)
        if payload.get("captchaOrder") is None
        else payload["captchaOrder"].split(",")
    )
    supplied = payload.get("captcha_token")
    path = native_secret_path(payload, root)
    if path is not None:
        try:
            supplied = read_native_token_file(path)
        finally:
            path.unlink(missing_ok=True)
    if supplied is not None:
        budget = 1
    else:
        configured_provider_keys(
            ProviderKeys(Path.home() / ".config/homelab"),
            names,
            require_all=payload.get("captchaOrder") is not None,
        )
    stats = CaptchaStats(root)
    previous: set[str] = set()
    for index in range(budget):
        selection: dict[str, str | None] = {"chosen": None}
        token_state = {"consumed": False}
        override = VideoOverrides(
            project,
            payload.get("count", 1),
            token=lambda page: asyncio.sleep(0, result=""),
            metadata_required=supplied is None,
            previous_request_ids=previous,
        )

        async def mint(
            page: Any,
            override: VideoOverrides = override,
            selection: dict[str, str | None] = selection,
            token_state: dict[str, bool] = token_state,
        ) -> str:
            nonlocal supplied
            if token_state["consumed"] or override.closed or not override.page_matches(page):
                raise SolverError("Video CAPTCHA scope is closed or mismatched")
            token_state["consumed"] = True
            if supplied is not None:
                token, supplied = supplied, None
                selection["chosen"] = "supplied"
                override.provider_name = "supplied"
                return token
            keys = ProviderKeys(Path.home() / ".config/homelab")
            configured = configured_provider_keys(
                keys, names, require_all=payload.get("captchaOrder") is not None
            )
            metadata = override.metadata
            url = str(page.url)
            if (
                metadata is None
                or metadata.get("action") != "VIDEO_GENERATION"
                or override.metadata_url != url
                or not 0 <= time.monotonic() - override.metadata_at <= 120
            ):
                raise SolverError("Fresh video CAPTCHA metadata is unavailable")
            key = await asyncio.wait_for(discover_site_key(page), timeout=10)
            if key != metadata.get("sitekey") or str(page.url) != url:
                raise SolverError("Current video CAPTCHA metadata differs from trusted page")
            for name, secret in configured:
                if str(page.url) != url or override.closed or not override.page_matches(page):
                    raise SolverError("Video CAPTCHA scope changed before solving")
                stats.record(name, "solveStarted")
                try:
                    solution = await asyncio.wait_for(
                        Solver().solve(name, secret, url, key, "VIDEO_GENERATION"), timeout=120
                    )
                    token = validate_native_captcha_token(solution.token)
                except (SolverError, ConfigurationError, TimeoutError):
                    if override.closed:
                        raise SolverError("Video CAPTCHA scope closed during solving") from None
                    stats.record(name, "solveFailed")
                    continue
                if str(page.url) != url or override.closed:
                    raise SolverError("Video CAPTCHA scope changed during solving")
                selection["chosen"] = name
                override.provider_name = name
                stats.record(name, "solved")
                return token
            raise SolverError("Configured video providers failed before Google submission")

        def observe(phase: str, selection: dict[str, str | None] = selection) -> None:
            chosen = selection["chosen"]
            if chosen is not None:
                stats.record(chosen, phase)

        override.token = mint
        override.observe = observe
        handle = active_video_overrides.set(override)
        try:
            return await attempt(override), selection["chosen"]
        except WafRejectionError:
            if (
                path is not None
                or payload.get("captcha_token") is not None
                or index + 1 >= budget
                or not override.dispatched
                or override.terminal != "rejected"
                or override.known_media_ids
            ):
                raise
        finally:
            override.close()
            active_video_overrides.reset(handle)
    raise AssertionError("Video CAPTCHA policy exhausted without result")
