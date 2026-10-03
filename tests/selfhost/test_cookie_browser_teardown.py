"""Exercise real importer teardown with fake Playwright contexts, never network."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import AuthMissingError
from gflow_cli.profile_lease import ProfileLease
from gflow_cli.selfhost.profile_import import _populate_candidate
from gflow_cli.selfhost.session_import import parse_cookie_table


@pytest.fixture
def fake_browser(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    page = SimpleNamespace(goto=AsyncMock(), wait_for_timeout=AsyncMock())
    browser = SimpleNamespace(close=AsyncMock())
    context = SimpleNamespace(
        add_cookies=AsyncMock(),
        new_page=AsyncMock(return_value=page),
        close=AsyncMock(),
        browser=browser,
    )
    launcher = AsyncMock(return_value=context)
    manager = AsyncMock()
    manager.__aenter__.return_value = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launcher)
    )
    monkeypatch.setattr("gflow_cli.auth.strategies.async_playwright", lambda: manager)
    monkeypatch.setattr(
        "gflow_cli.auth.internal_chromium.login_launch_kwargs",
        lambda path, headless, **kwargs: {"user_data_dir": str(path), "headless": headless},
    )
    table = parse_cookie_table("SID\tfixture-value\t.google.com\t/\tSession")
    return candidate, table, page, context, browser, launcher, manager


@pytest.mark.asyncio
async def test_population_success_closes_context_and_releases_profile(fake_browser):
    path, table, page, context, _, launch, manager = fake_browser
    await _populate_candidate(path, table)
    assert launch.await_args.kwargs["headless"] is False
    context.add_cookies.assert_awaited_once()
    page.goto.assert_awaited_once()
    context.close.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()
    with ProfileLease(path):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["add_cookies", "goto", "wait"])
async def test_population_cancel_closes_context_and_releases_profile(fake_browser, stage):
    path, table, page, context, _, _, manager = fake_browser
    operation = {
        "add_cookies": context.add_cookies,
        "goto": page.goto,
        "wait": page.wait_for_timeout,
    }[stage]
    operation.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _populate_candidate(path, table)
    context.close.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()
    with ProfileLease(path):
        pass


@pytest.mark.asyncio
async def test_graceful_close_failure_attempts_force_close_and_refuses_success(fake_browser):
    path, table, _, context, browser, _, manager = fake_browser
    context.close.side_effect = RuntimeError("simulated close failure")
    with pytest.raises(AuthMissingError):
        await _populate_candidate(path, table)
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()
    with ProfileLease(path):
        pass


@pytest.mark.asyncio
async def test_cancel_during_context_close_still_force_closes(fake_browser):
    path, table, _, context, browser, _, manager = fake_browser
    context.close.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _populate_candidate(path, table)
    browser.close.assert_awaited_once()
    manager.__aexit__.assert_awaited_once()
    with ProfileLease(path):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_import_cleanup_failure_preserves_original_safe_error(monkeypatch, cancelled):
    from gflow_cli import auth
    from gflow_cli.selfhost import profile_import as module

    table = parse_cookie_table("SID\tfixture-value\t.google.com\t/\tSession")

    async def fail_populate(path, table):
        if cancelled:
            raise asyncio.CancelledError()
        raise RuntimeError("private-cookie-value")

    def denied_cleanup(path):
        raise OSError("private-cookie-value")

    monkeypatch.setattr(module, "_populate_candidate", fail_populate)
    monkeypatch.setattr(module.shutil, "rmtree", denied_cleanup)
    expected = asyncio.CancelledError if cancelled else AuthMissingError
    with pytest.raises(expected) as caught:
        await module.import_cookie_profile(table, "quarantined")
    assert "private-cookie-value" not in str(caught.value)
    assert not auth.profile_dir("quarantined").exists()
    remaining = list((auth.default_profile_root() / ".cookie-staging").iterdir())
    assert len(remaining) == 1 and remaining[0].stat().st_mode & 0o077 == 0


@pytest.mark.asyncio
async def test_population_engine_guard_runs_under_lease_before_launch(fake_browser, monkeypatch):
    from gflow_cli.errors import ProfileEngineDowngradeError, ProfileLockedError

    path, table, _, _, _, launch, _ = fake_browser
    observed = []

    def guard(profile, channel):
        assert profile == path and channel == "chrome"
        with pytest.raises(ProfileLockedError), ProfileLease(path):
            pass
        observed.append("guard")
        raise ProfileEngineDowngradeError("simulated")

    monkeypatch.setattr("gflow_cli.browser_manager.ensure_profile_engine_compatible", guard)
    with pytest.raises(ProfileEngineDowngradeError):
        await _populate_candidate(path, table)
    assert observed == ["guard"]
    launch.assert_not_awaited()
    with ProfileLease(path):
        pass
