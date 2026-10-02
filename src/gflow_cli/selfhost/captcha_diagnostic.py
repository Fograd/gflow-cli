"""Abort-only CAPTCHA observations. Never creates a solver task or prints secret fields."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest
from gflow_cli.api.transports.migrated_image_overrides import (
    ImageOverrides,
    active_overrides,
    reload_metadata,
)
from gflow_cli.config import get_settings


def anchor_metadata(url: str) -> dict[str, Any] | None:
    if len(url) > 16384:
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ("www.google.com", "www.recaptcha.net")
        or parsed.path != "/recaptcha/enterprise/anchor"
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        return None
    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=100)
    keys = query.get("k", [])
    if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", keys[0]):
        return None
    return {
        "sitekey": keys[0],
        "sPresence": bool(query.get("s", [""])[0]),
        "apiDomain": parsed.hostname,
    }


async def capture(profile: str, project: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.flow_host != "flow.google.com" or settings.transport not in (None, "ui_automation"):
        raise ValueError("Diagnostic requires explicit native Flow host and UI automation")
    result: dict[str, Any] = {
        "scope": "one-aborted-image-request",
        "anchors": [],
        "reload": None,
        "cookieNames": [],
        "generationAborted": False,
        "renderObserved": False,
        "solverCalled": False,
    }

    async def stop(page: Any) -> str:
        result["generationAborted"] = True
        raise ValueError("Diagnostic abort before Google generation")

    override = ImageOverrides(project, 1, token=stop)
    state = active_overrides.set(override)
    try:
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(profile), headless=False, transport="ui_automation"
        ) as client:
            context = client._context  # pyright: ignore[reportPrivateUsage]
            if context is None:
                raise RuntimeError("Diagnostic browser context unavailable")

            def observe(request: Any) -> None:
                try:
                    anchor = anchor_metadata(str(request.url))
                    if anchor and anchor not in result["anchors"] and len(result["anchors"]) < 10:
                        result["anchors"].append(anchor)
                    reload = reload_metadata(str(request.url), request.post_data_buffer or b"")
                    if reload:
                        result["reload"] = reload
                except (ValueError, TypeError, AttributeError):
                    return

            async def block(route: Any) -> None:
                raw = route.request.post_data or ""
                if (
                    "ogiZ0b" in raw
                    or "ogiZ0b" in route.request.url
                    or (
                        urlsplit(str(route.request.url)).hostname == "aisandbox-pa.googleapis.com"
                        and route.request.method == "POST"
                    )
                ):
                    result["generationAborted"] = True
                    await route.abort()
                else:
                    await route.continue_()

            context.on("request", observe)
            await context.route("**/*", block)
            try:
                await client.generate_image(
                    project_id=project,
                    req=GenerateImageRequest(prompt="A blue sphere", aspect=Aspect.SQUARE),
                )
            except Exception as error:
                result["errorClass"] = type(error).__name__
            finally:
                context.remove_listener("request", observe)
                await context.unroute("**/*", block)
            cookies = await context.cookies(["https://flow.google.com", "https://www.google.com"])
            result["cookieNames"] = sorted(
                {
                    cookie.get("name", "")
                    for cookie in cookies
                    if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", cookie.get("name", ""))
                }
            )
            if context.pages:
                result["browserUserAgent"] = await context.pages[0].evaluate("navigator.userAgent")
            reload = result["reload"]
            result["anchorReloadKeyAgreement"] = (
                all(anchor["sitekey"] == reload["sitekey"] for anchor in result["anchors"])
                if reload and result["anchors"]
                else None
            )
    finally:
        active_overrides.reset(state)
    result["status"] = "aborted-read" if result["generationAborted"] else "incomplete-read"
    return result


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m gflow_cli.selfhost.captcha_diagnostic PROFILE PROJECT")
    sys.stdout.write(
        json.dumps(asyncio.run(capture(sys.argv[1], sys.argv[2])), sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
