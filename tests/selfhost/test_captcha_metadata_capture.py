from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from gflow_cli.api.transports.migrated_image_overrides import (
    CAPTCHA_METADATA_JS,
    CLEANUP_CAPTCHA_JS,
    ImageOverrides,
)


async def test_scoped_hook_observes_execute_and_restores_original():
    if not Path("/usr/bin/google-chrome").exists():
        pytest.skip("System Chrome required for browser hook regression")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]
        )
        page = await browser.new_page()
        await page.goto("data:text/html,<html></html>")
        await page.evaluate(
            "() => {window.grecaptcha={enterprise:{execute:(key, opts)=>"
            "Promise.resolve('fixture-token')}};"
            "window.originalFixture=window.grecaptcha.enterprise.execute;}"
        )
        assert await page.evaluate(CAPTCHA_METADATA_JS) is True
        await page.evaluate(
            "() => window.grecaptcha.enterprise.execute("
            "'observed-sitekey',{action:'observed-action'})"
        )
        assert await page.evaluate("() => window.__gflowCaptchaMetadata") == {
            "sitekey": "observed-sitekey",
            "action": "observed-action",
        }
        await page.evaluate(CLEANUP_CAPTCHA_JS)
        assert await page.evaluate(
            "() => window.grecaptcha.enterprise.execute === window.originalFixture"
        )
        assert await page.evaluate("() => typeof window.__gflowCaptchaMetadata") == "undefined"
        await browser.close()


async def test_supplied_token_needs_no_browser_metadata():
    async def supplied(page):
        return "t" * 30

    override = ImageOverrides("project", 1, token=supplied, metadata_required=False)
    assert not override.metadata_required


def test_provider_generation_guard_is_501_before_queue(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.server import create_app

    class Keys:
        def public(self):
            return {"CapSolver": {"configured": True}}

    monkeypatch.setattr("gflow_cli.selfhost.captcha_routes.provider_keys", lambda: Keys())
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "first", "project": "11111111-1111-4111-8111-111111111111"}},
    )
    cfg.sync_wait = 0
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for field, value in (("captchaOrder", "CapSolver"), ("captchaRetry", 1)):
            result = client.post(
                "/v1/google-flow/images",
                headers={"Authorization": "Bearer test"},
                json={"prompt": "fixture", field: value},
            )
            assert result.status_code == 501
            assert "unmeasured" in result.json()["detail"]["feature"]
        assert client.app.state.store.job_page(limit=100)["jobs"] == []
