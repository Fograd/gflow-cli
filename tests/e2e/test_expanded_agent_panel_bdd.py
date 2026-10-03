"""Opt-in zero-submit proof of the measured expanded-panel recovery."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/expanded_agent_panel.feature")


@given("an explicitly configured migrated composer recovery probe", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_COMPOSER_RECOVERY") != "expanded-panel":
        pytest.skip("Explicit no-submit composer probe required")
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()):
        pytest.skip("Private authenticated profile/home/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    reset_settings()
    values["generation_requests"] = 0
    return values


@when("the expanded chat hides its chip and composer recovery runs")
def recover(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            try:

                async def guard(route):
                    request = route.request
                    if any(
                        rpc in request.url or rpc in (request.post_data or "")
                        for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6")
                    ):
                        case["generation_requests"] += 1
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                await page.goto(
                    "https://flow.google.com/project/" + case["RESOURCES_PROJECT"],
                    wait_until="domcontentloaded",
                )
                await page.locator("flow-creative-agent-prompt-box").wait_for(
                    state="visible", timeout=15000
                )
                chip = page.locator("button.agent-mode-chip")
                if await chip.count():
                    assert await chip.count() == 1
                    if await chip.get_attribute("aria-pressed") == "false":
                        await chip.click()
                    expand = page.locator("button:visible").filter(
                        has=page.locator("mat-icon:text-is('expand_content')")
                    )
                    assert await expand.count() == 1
                    await expand.click()
                close = page.locator("flow-agent-panel button.header-action:visible").filter(
                    has=page.locator("mat-icon:text-is('close')")
                )
                await close.wait_for(state="visible", timeout=5000)
                await chip.wait_for(state="detached", timeout=5000)
                assert await chip.count() == 0
                await MigratedComposer().ensure_editor(page, case["RESOURCES_PROJECT"], timeout_s=1)
                case["ready"] = await page.locator(".settings-trigger-button").is_visible()
                case["pressed"] = await page.locator(
                    "button.agent-mode-chip[aria-pressed='true']"
                ).count()
            finally:
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 75))


@then("classic settings are visible without any generation request")
def verified(case):
    assert case["ready"] is True
    assert case["pressed"] == 0
    assert case["generation_requests"] == 0
