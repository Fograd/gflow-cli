"""Real intercepted Patchright menu; no external request or authenticated profile."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports import migrated_upscale as transport
from gflow_cli.config import reset_settings
from tests.api.test_image_upscale_capabilities import M, P

scenarios("../features/image_upscale_capabilities_live.feature")


def markup(variant):
    four = (
        ""
        if variant == "missing"
        else (
            '<button role="menuitem"'
            + (' disabled aria-disabled="true"' if variant == "enabled_disabled" else "")
            + ">4K</button>"
        )
    )
    if variant == "duplicate":
        four += '<button role="menuitem" aria-disabled="true">4K</button>'
    extra = (
        "<button><mat-icon>download</mat-icon></button>" if variant == "duplicate_trigger" else ""
    )
    menu = (
        ""
        if variant == "no_menu"
        else (
            '<div role="menu" id="menu" hidden>'
            '<button role="menuitem">2K</button>' + four + "</div>"
        )
    )
    return (
        '<html><body data-target-clicks="0">'
        '<button id="download"><mat-icon>download</mat-icon></button>'
        + extra
        + menu
        + """
        <script>
        document.getElementById("download").addEventListener("click", () => {
            const menu = document.getElementById("menu");
            if (menu) menu.hidden = false;
        });
        document.querySelectorAll('[role="menuitem"]').forEach(item =>
            item.addEventListener("click", () => document.body.dataset.targetClicks++)
        );
        </script></body></html>"""
    )


@given("an explicitly enabled intercepted Patchright image detail menu", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_UPSCALE_CAPABILITIES") != "1":
        pytest.skip("Explicit intercepted browser opt-in required")
    pytest.importorskip("patchright.async_api")
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", "patchright")
    reset_settings()
    monkeypatch.setattr(
        transport,
        "lookup_asset",
        AsyncMock(return_value=SimpleNamespace(project_id=P, media_id=M, kind="image")),
    )
    monkeypatch.setattr(
        transport, "TokenMinter", lambda *args, **kwargs: pytest.fail("Token mint forbidden")
    )
    return {"results": {}, "target_clicks": 0, "external_requests": 0, "generation_requests": 0}


@when("the shared capability inspector observes the menu variants")
def observe(case):
    from patchright.async_api import async_playwright

    async def run():
        async with async_playwright() as driver:
            options = {"headless": True}
            executable = os.getenv("GFLOW_CLI_E2E_CAPABILITIES_BROWSER")
            if executable:
                options["executable_path"] = executable
            browser = await driver.chromium.launch(**options)
            try:
                variants = (
                    "enabled_disabled",
                    "both_enabled",
                    "missing",
                    "duplicate",
                    "duplicate_trigger",
                    "no_menu",
                )
                for variant in variants:
                    context = await browser.new_context()
                    try:

                        def intercept_variant(variant):
                            async def route(request):
                                url = request.request.url
                                if "SPrCad" in url or "batchexecute" in url:
                                    case["generation_requests"] += 1
                                    await request.abort()
                                    return
                                if not url.startswith("https://flow.google.com/"):
                                    case["external_requests"] += 1
                                    await request.abort()
                                    return
                                await request.fulfill(
                                    status=200, content_type="text/html", body=markup(variant)
                                )

                            return route

                        await context.route("**/*", intercept_variant(variant))
                        page = await context.new_page()
                        checked = []
                        client = SimpleNamespace(
                            _checkout_page=AsyncMock(return_value=page),
                            _checkin_page=checked.append,
                        )
                        result = await FlowApiClient.get_image_upscale_capabilities(
                            client, project_id=P, media_id=M
                        )
                        assert checked == [page]
                        case["results"][variant] = result["capabilities"]
                        body = await page.query_selector("body")
                        assert body is not None
                        if body is not None:
                            case["target_clicks"] += int(
                                await body.get_attribute("data-target-clicks") or "0"
                            )
                    finally:
                        await context.close()
            finally:
                await browser.close()

    asyncio.run(asyncio.wait_for(run(), 90))
    reset_settings()


@then("states remain distinct and no generation target is selected")
def verified(case):
    def states(variant):
        return [row["status"] for row in case["results"][variant]]

    assert states("enabled_disabled") == ["available", "disabled"]
    assert states("both_enabled") == ["available", "available"]
    assert states("missing") == ["available", "unknown"]
    assert states("duplicate") == ["available", "unknown"]
    assert states("duplicate_trigger") == ["unknown", "unknown"]
    assert states("no_menu") == ["unknown", "unknown"]
    assert case["target_clicks"] == case["external_requests"] == case["generation_requests"] == 0
    print(
        "intercepted_patchright_menu_variants",
        len(case["results"]),
        "target_clicks",
        0,
        "external_requests",
        0,
        "generation_requests",
        0,
    )
