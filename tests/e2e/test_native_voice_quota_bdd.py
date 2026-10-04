"""Real browser, intercepted native TTS replies; no Google traffic or paid preview."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

from pytest_bdd import given, scenarios, then, when

from gflow_cli.api._engine import resolve_async_playwright
from gflow_cli.api.transports import native_voices
from gflow_cli.config import reset_settings
from gflow_cli.errors import NativeQuotaError, VoiceMutationUnknownError
from tests.api.test_native_quota_producers import refusal

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
scenarios("../features/native_voice_quota.feature")


@given("a real browser with every native TTS request intercepted", target_fixture="case")
def configured(monkeypatch):
    engine = os.getenv("GFLOW_CLI_E2E_LOGIN_ENGINE", "playwright")
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", engine)
    reset_settings()
    return {"engine": engine, "rpcs": []}


@when("Google explicitly refuses the preview with a unique quota reason")
def preview(case):
    drive(case, False)


@when("the preview is accepted but its metadata save is quota refused")
def save(case):
    drive(case, True)


def drive(case, save_failure):
    async def run():
        async with resolve_async_playwright(case["engine"])() as pw:
            browser = await pw.chromium.launch(channel="chrome", headless=True)
            try:
                context = await browser.new_context()

                async def serve(route):
                    if "/batchexecute?" in route.request.url:
                        payload = json.loads(parse_qs(route.request.post_data)["f.req"][0])
                        rpc = payload[0][0][0]
                        case["rpcs"].append(rpc)
                        assert len(case["rpcs"]) <= 2
                        if save_failure and rpc == native_voices.PREVIEW_RPC:
                            wire = json.dumps([["wrb.fr", rpc, json.dumps([[[M, P, W]], []])]])
                        else:
                            wire = refusal(rpc, "PUBLIC_ERROR_USER_REQUESTS_THROTTLED")
                        await route.fulfill(status=200, body=wire)
                    else:
                        await route.fulfill(
                            status=200,
                            content_type="text/html",
                            body="<script>window.WIZ_global_data={cfb2h:'synthetic',FdrFJe:'synthetic',SNlM0e:'synthetic'}</script>",
                        )

                await context.route("**/*", serve)
                page = await context.new_page()
                await page.goto("https://flow.google.com/project/" + P)
                with (
                    patch(
                        "gflow_cli.api.transports.migrated_resources.read_project_payload",
                        AsyncMock(return_value=[]),
                    ),
                    patch.object(
                        native_voices, "_mint_audio_token", AsyncMock(return_value="synthetic")
                    ),
                ):
                    try:
                        await native_voices.create_saved_voice(
                            page, P, "Guide", "Charon", "Hello", "Warm"
                        )
                    except (NativeQuotaError, VoiceMutationUnknownError) as error:
                        case["error"] = error
            finally:
                await browser.close()

    try:
        asyncio.run(asyncio.wait_for(run(), 30))
    finally:
        reset_settings()


@then("one preview returns a terminal quota refusal without a save or replay")
def terminal(case):
    assert case["rpcs"] == [native_voices.PREVIEW_RPC]
    assert isinstance(case["error"], NativeQuotaError)
    assert case["error"].reason == "PUBLIC_ERROR_USER_REQUESTS_THROTTLED"
    assert case["error"].retryable is False


@then("the accepted audio handles remain recoverable and the preview is never replayed")
def recoverable(case):
    assert case["rpcs"] == [native_voices.PREVIEW_RPC, native_voices.SAVE_MEDIA_RPC]
    assert isinstance(case["error"], VoiceMutationUnknownError)
    proof = case["error"].to_problem_details()
    assert proof["known_media_ids"] == [M]
    assert proof["workflow_ids"] == [W]
    assert proof["phase"] == "save"
