"""A migrated cookie jar cannot close a login whose live principal is refused."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gflow_cli.auth.internal_chromium import poll_session_until_authenticated
from gflow_cli.auth.verification import FlowSessionOutcome


def case():
    page = MagicMock()
    page.url = "https://flow.google.com/u/0/"
    page.is_closed.return_value = False
    response = MagicMock(status=200)
    response.text = AsyncMock(return_value="{}")
    page.request.get = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.cookies = AsyncMock(
        return_value=[
            {"name": "SAPISID", "value": "synthetic", "domain": ".google.com"},
            {"name": "__Secure-OSID", "value": "synthetic", "domain": ".flow.google.com"},
        ]
    )
    return ctx, page


async def test_refused_principal_keeps_window_until_user_closes():
    ctx, page = case()
    principal = AsyncMock(side_effect=ValueError("synthetic refusal"))
    page.is_closed.side_effect = [False, False, True]
    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", principal),
        patch(
            "gflow_cli.auth.internal_chromium._landed_on_public_page", AsyncMock(return_value=False)
        ),
        patch("gflow_cli.auth.internal_chromium.asyncio.sleep", AsyncMock()),
    ):
        result = await poll_session_until_authenticated(
            ctx, page, 10, "chrome", raise_on_close=False
        )
    assert result is None
    assert principal.await_count == 2


async def test_fresh_principal_after_refusal_ends_wait():
    ctx, page = case()
    principal = AsyncMock(side_effect=[ValueError("synthetic refusal"), "synthetic@example.test"])
    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", principal),
        patch(
            "gflow_cli.auth.internal_chromium._landed_on_public_page", AsyncMock(return_value=False)
        ),
        patch("gflow_cli.auth.internal_chromium.asyncio.sleep", AsyncMock()),
    ):
        result = await poll_session_until_authenticated(
            ctx, page, 10, "chrome", raise_on_close=False
        )
    assert result is not None
    assert result.outcome is FlowSessionOutcome.AUTHENTICATED
    assert result.user_email == "synthetic@example.test"
    assert principal.await_count == 2


async def test_cancelled_principal_never_becomes_a_success():
    ctx, page = case()
    principal = AsyncMock(side_effect=asyncio.CancelledError())
    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", principal),
        patch(
            "gflow_cli.auth.internal_chromium._landed_on_public_page", AsyncMock(return_value=False)
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await poll_session_until_authenticated(ctx, page, 10, "chrome", raise_on_close=False)


async def test_native_deadline_remains_within_login_budget():
    from gflow_cli.errors import AuthLoginTimeoutError

    ctx, page = case()

    async def blocked(_page):
        await asyncio.sleep(60)

    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", blocked),
        patch(
            "gflow_cli.auth.internal_chromium._landed_on_public_page", AsyncMock(return_value=False)
        ),
        patch("gflow_cli.auth.internal_chromium.POLL_INTERVAL_SECONDS", 0.01),
        pytest.raises(AuthLoginTimeoutError),
    ):
        await asyncio.wait_for(
            poll_session_until_authenticated(ctx, page, 0.05, "chrome", raise_on_close=False),
            timeout=0.5,
        )


async def test_navigation_during_principal_read_cannot_complete_login():
    ctx, page = case()
    page.is_closed.side_effect = [False, True]

    async def changed(_page):
        page.url = "https://accounts.google.com/v3/signin/challenge/pwd"
        return "synthetic@example.test"

    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", changed),
        patch(
            "gflow_cli.auth.internal_chromium._landed_on_public_page", AsyncMock(return_value=False)
        ),
        patch("gflow_cli.auth.internal_chromium.asyncio.sleep", AsyncMock()),
    ):
        result = await poll_session_until_authenticated(
            ctx, page, 10, "chrome", raise_on_close=False
        )
    assert result is None


async def test_owned_login_resolves_configured_engine(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from gflow_cli.auth.real_chrome import RealChromeStrategy
    from gflow_cli.profile_lease import ProfileLease

    strategy = RealChromeStrategy()
    context = MagicMock()
    context.close = AsyncMock()
    driver = MagicMock()
    driver.chromium.launch_persistent_context = AsyncMock(return_value=context)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=driver)
    manager.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=manager)
    resolver = MagicMock(return_value=factory)
    monkeypatch.setattr(ProfileLease, "acquire", lambda self: self)
    monkeypatch.setattr(ProfileLease, "release", lambda self: None)
    monkeypatch.setattr(strategy, "_await_flow_session", AsyncMock())
    with (
        patch(
            "gflow_cli.auth.real_chrome.get_settings",
            return_value=SimpleNamespace(browser_engine="patchright"),
        ),
        patch("gflow_cli.auth.real_chrome.login_launch_kwargs", return_value={}),
        patch("gflow_cli.api._engine.resolve_async_playwright", resolver),
    ):
        assert await strategy._login_owned_browser(tmp_path, False) is None
    resolver.assert_called_once_with("patchright")
    factory.assert_called_once()
    context.close.assert_awaited_once()


async def test_google_challenge_during_post_read_settle_cannot_complete_login():
    ctx, page = case()
    page.is_closed.side_effect = [False, True]
    calls = 0

    async def settle(_page):
        nonlocal calls
        calls += 1
        if calls == 2:
            page.url = "https://accounts.google.com/v3/signin/challenge/pwd"
        return False

    with (
        patch(
            "gflow_cli.auth.native_identity.read_native_identity",
            AsyncMock(return_value="synthetic@example.test"),
        ),
        patch("gflow_cli.auth.internal_chromium._landed_on_public_page", settle),
        patch("gflow_cli.auth.internal_chromium.asyncio.sleep", AsyncMock()),
    ):
        result = await poll_session_until_authenticated(
            ctx, page, 10, "chrome", raise_on_close=False
        )
    assert result is None


async def test_public_landing_during_read_preserves_recheck_on_close():
    from gflow_cli.errors import IdentityRecheckPendingError

    ctx, page = case()
    page.is_closed.side_effect = [False, True]

    async def changed(_page):
        page.url = "https://flow.google.com/about"
        return "synthetic@example.test"

    async def settle(_page):
        return page.url.endswith("/about")

    with (
        patch("gflow_cli.auth.native_identity.read_native_identity", changed),
        patch("gflow_cli.auth.internal_chromium._landed_on_public_page", settle),
        patch("gflow_cli.auth.internal_chromium.asyncio.sleep", AsyncMock()),
        pytest.raises(IdentityRecheckPendingError),
    ):
        await poll_session_until_authenticated(ctx, page, 10, "chrome", raise_on_close=False)
