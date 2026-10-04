"""Measured Google cookie bar actions use structural selectors and normal clicks."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.transports.migrated_composer import (
    COOKIE_BAR,
    COOKIE_BAR_REJECT,
    MigratedComposer,
)

ACCEPT = "button.glue-cookie-notification-bar__accept"
MORE = "a.glue-cookie-notification-bar__more"


def observed_bar(*, reject=False, accept=True, visible=True, stuck=False):
    actions = {}
    for selector, present in ((COOKIE_BAR_REJECT, reject), (ACCEPT, accept), (MORE, True)):
        node = MagicMock(spec=["first", "count", "click"])
        node.first = node
        node.count = AsyncMock(return_value=int(present))
        node.click = AsyncMock(
            side_effect=PlaywrightTimeoutError("Timeout 3000ms exceeded")
            if stuck or not present
            else None
        )
        actions[selector] = node
    bar = MagicMock(spec=["first", "is_visible", "locator", "wait_for"])
    bar.first = bar
    bar.is_visible = AsyncMock(return_value=visible)
    bar.locator.side_effect = lambda selector: actions[selector]
    bar.wait_for = AsyncMock()
    page = MagicMock(spec=["locator"])
    page.locator.side_effect = lambda selector: bar if selector == COOKIE_BAR else None
    return page, bar, actions


@pytest.mark.asyncio
async def test_measured_accept_only_bar_clicks_actual_action_then_waits_hidden():
    # Root no-generation DOM: visible COOKIE_BAR; A.more "Learn more";
    # BUTTON.accept "OK, got it"; no BUTTON.reject. Labels never select anything.
    page, bar, actions = observed_bar()
    await MigratedComposer()._dismiss_cookie_bar(page)  # noqa: SLF001
    actions[ACCEPT].click.assert_awaited_once_with(timeout=3000)
    actions[COOKIE_BAR_REJECT].click.assert_not_awaited()
    actions[MORE].click.assert_not_awaited()
    bar.wait_for.assert_awaited_once_with(state="hidden", timeout=3000)


@pytest.mark.asyncio
async def test_reject_remains_preferred_when_both_actions_exist():
    page, bar, actions = observed_bar(reject=True)
    await MigratedComposer()._dismiss_cookie_bar(page)  # noqa: SLF001
    actions[COOKIE_BAR_REJECT].click.assert_awaited_once_with(timeout=3000)
    actions[ACCEPT].click.assert_not_awaited()
    actions[MORE].click.assert_not_awaited()
    bar.wait_for.assert_awaited_once_with(state="hidden", timeout=3000)


@pytest.mark.asyncio
async def test_failed_present_reject_does_not_fall_through_to_accept():
    page, bar, actions = observed_bar(reject=True, stuck=True)
    await MigratedComposer()._dismiss_cookie_bar(page)  # noqa: SLF001
    actions[COOKIE_BAR_REJECT].click.assert_awaited_once_with(timeout=3000)
    actions[ACCEPT].click.assert_not_awaited()
    bar.wait_for.assert_not_awaited()


@pytest.mark.asyncio
async def test_absent_cookie_bar_never_reads_or_clicks_actions():
    page, bar, actions = observed_bar(visible=False)
    await MigratedComposer()._dismiss_cookie_bar(page)  # noqa: SLF001
    bar.locator.assert_not_called()
    bar.wait_for.assert_not_awaited()
    for action in actions.values():
        action.click.assert_not_awaited()
