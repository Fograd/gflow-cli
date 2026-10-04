"""Real intercepted Patchright credits; no external/authenticated/paid request."""

import asyncio
import json
from urllib.parse import parse_qs

from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.native_credits import read_native_credits
from gflow_cli.config import reset_settings

scenarios("../features/native_credits_context.feature")


@given("a real Patchright browser with all credit requests intercepted", target_fixture="case")
def configured(monkeypatch):
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", "patchright")
    reset_settings()
    return {"rpcs": []}


@when("the SDK reads the native credit balance")
def read(case):
    from patchright.async_api import async_playwright

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel="chrome", headless=True)
            try:
                context = await browser.new_context()

                async def serve(route):
                    if "/batchexecute?" in route.request.url:
                        payload = json.loads(parse_qs(route.request.post_data)["f.req"][0])
                        rpc = payload[0][0][0]
                        case["rpcs"].append(rpc)
                        assert rpc == "nzlxg"
                        wire = json.dumps([["wrb.fr", rpc, json.dumps([42, 1, None, 2])]])
                        await route.fulfill(status=200, body=wire)
                    else:
                        await route.fulfill(
                            status=200,
                            content_type="text/html",
                            body="<script>window.WIZ_global_data={cfb2h:'synthetic',FdrFJe:'synthetic',SNlM0e:'synthetic'}</script>",
                        )

                await context.route("**/*", serve)
                page = await context.new_page()
                await page.goto("https://flow.google.com/")
                case["info"] = await read_native_credits(page)
            finally:
                await browser.close()

    try:
        asyncio.run(asyncio.wait_for(run(), 30))
    finally:
        reset_settings()


@then("one native read returns the observed credit balance without a mint")
def observed(case):
    assert case["rpcs"] == ["nzlxg"]
    assert case["info"].credits == 42
    assert case["info"].service_tier == "SERVICE_TIER_INTERMEDIATE"
    assert case["info"].subscription_credits is None
