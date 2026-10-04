"""Real intercepted browser MP4 ingestion; no Google traffic or credentials."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

from pytest_bdd import given, scenarios, then, when

from gflow_cli.api._engine import resolve_async_playwright
from gflow_cli.api.transports.migrated_video_upload import _upload_video_snapshot
from gflow_cli.config import reset_settings

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
scenarios("../features/native_video_dialog.feature")


@given(
    "an intercepted real browser with the current three-button video rights dialog",
    target_fixture="case",
)
def case(monkeypatch, tmp_path):
    engine = os.getenv("GFLOW_CLI_E2E_LOGIN_ENGINE", "patchright")
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", engine)
    reset_settings()
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"\x00\x00\x00\x0cftypisom")
    return {"engine": engine, "path": path, "uploads": 0}


@when("gflow uploads an explicitly owned synthetic MP4")
def upload(case):
    async def run():
        async with resolve_async_playwright(case["engine"])() as pw:
            browser = await pw.chromium.launch(channel="chrome", headless=True)
            try:
                context = await browser.new_context()
                html = (
                    "<button><mat-icon>add</mat-icon></button>"
                    '<div class="cdk-overlay-pane"><button role="menuitem" '
                    "onclick=\"document.querySelector('input').click()\">"
                    "<mat-icon>upload</mat-icon></button></div>"
                    '<input type="file" onchange="showDialog()">'
                    '<script>document.body.dataset.persistent="false";function showDialog(){'
                    'const d=document.createElement("mat-dialog-container");'
                    'const cancel=document.createElement("button");'
                    'cancel.textContent="Cancel";d.append(cancel);'
                    'const persistent=document.createElement("button");'
                    'persistent.textContent="Agree persistently";'
                    'persistent.onclick=()=>{document.body.dataset.persistent="true"};'
                    "d.append(persistent);"
                    'const once=document.createElement("button");'
                    'once.textContent="Agree once";once.onclick=sendUpload;d.append(once);'
                    "document.body.append(d);}async function sendUpload(){"
                    'await fetch("/upload/v1/flow/upload/video/' + P + '",'
                    '{method:"POST",body:"synthetic"});}</script>'
                )

                async def serve(route):
                    if "/upload/v1/flow/upload/video/" in route.request.url:
                        case["uploads"] += 1
                        assert case["uploads"] == 1
                        await route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({"mediaId": M, "media": {"name": M, "projectId": P}}),
                        )
                    else:
                        await route.fulfill(status=200, content_type="text/html", body=html)

                await context.route("**/*", serve)
                page = await context.new_page()
                await page.goto("https://flow.google.com/project/" + P)
                with patch(
                    "gflow_cli.api.transports.migrated_resources.read_project_payload",
                    AsyncMock(return_value=[]),
                ):
                    try:
                        case["result"] = await _upload_video_snapshot(
                            page, P, case["path"], rights_confirmed=True
                        )
                    except Exception as error:
                        case["error"] = type(error).__name__
                case["persistent"] = await page.locator("body").get_attribute("data-persistent")
            finally:
                await browser.close()

    try:
        asyncio.run(asyncio.wait_for(run(), 25))
    finally:
        reset_settings()


@then("exactly one upload succeeds and the persistent agreement is untouched")
def verified(case):
    assert case.get("result", (None,))[0] == M, case.get("error")
    assert case["uploads"] == 1
    assert case["persistent"] == "false"
