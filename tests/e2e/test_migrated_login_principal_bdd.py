"""Real browser, all origins intercepted, zero Google requests or credentials."""

import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pytest_bdd import given, scenarios, then, when

from gflow_cli.api._engine import resolve_async_playwright
from gflow_cli.auth.internal_chromium import poll_session_until_authenticated
from gflow_cli.config import reset_settings

scenarios("../features/migrated_login_principal.feature")


@given("a real Flow-origin browser with synthetic migrated cookies", target_fixture="case")
def configured(monkeypatch):
    engine = os.getenv("GFLOW_CLI_E2E_LOGIN_ENGINE", "playwright")
    assert engine in {"playwright", "patchright"}
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", engine)
    reset_settings()
    return {"engine": engine, "native_requests": 0}


@when("the native principal request is refused and the user closes the page")
def refused(case):
    _drive(case, False)


@when("a fresh principal is followed by navigation to a Google challenge")
def challenge(case):
    _drive(case, True)


def _drive(case, navigate):
    async def run():
        async with resolve_async_playwright(case["engine"])() as pw:
            browser = await pw.chromium.launch(channel="chrome", headless=True)
            try:
                context = await browser.new_context()
                await context.add_cookies(
                    [
                        {
                            "name": "SAPISID",
                            "value": "synthetic",
                            "domain": ".google.com",
                            "path": "/",
                            "secure": True,
                        },
                        {
                            "name": "__Secure-OSID",
                            "value": "synthetic",
                            "domain": ".flow.google.com",
                            "path": "/",
                            "secure": True,
                        },
                    ]
                )
                page = await context.new_page()

                async def close_after_refusal():
                    await asyncio.sleep(0.1)
                    if navigate:
                        await page.goto("https://accounts.google.com/v3/signin/challenge/pwd")
                        await asyncio.sleep(4)
                    await page.close()

                closer = None

                async def serve(route):
                    nonlocal closer
                    url = route.request.url
                    if "/batchexecute?" in url:
                        case["native_requests"] += 1
                        person = [None] * 10
                        person[9] = [[None, "synthetic@example.test"]]
                        payload = [[["me", 1, person]]]
                        body = json.dumps([["wrb.fr", "o30O0e", json.dumps(payload)]])
                        await route.fulfill(
                            status=200 if navigate else 401, body=body if navigate else ""
                        )
                        closer = asyncio.create_task(close_after_refusal())
                    elif "/fx/api/auth/session" in url:
                        await route.fulfill(status=200, content_type="application/json", body="{}")
                    else:
                        await route.fulfill(
                            status=200,
                            content_type="text/html",
                            body="<script>window.WIZ_global_data={cfb2h:'synthetic',FdrFJe:'synthetic',SNlM0e:'synthetic'}</script>",
                        )

                await context.route("**/*", serve)
                await page.goto("https://flow.google.com/u/0/")
                # APIRequestContext bypasses browser routes; stub the retired labs
                # oracle only. The native identity fetch runs in the real page.
                response = SimpleNamespace(status=200, text=AsyncMock(return_value="{}"))
                with patch.object(page.request, "get", AsyncMock(return_value=response)):
                    case["result"] = await poll_session_until_authenticated(
                        context, page, 15, "synthetic-e2e", raise_on_close=False
                    )
                if closer is not None:
                    await closer
            finally:
                await browser.close()

    try:
        asyncio.run(asyncio.wait_for(run(), 25))
    finally:
        reset_settings()


@then("cookie presence alone never completes the login")
def verified(case):
    assert case["native_requests"] == 1
    assert case["result"] is None
