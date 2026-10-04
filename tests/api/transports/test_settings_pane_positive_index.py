"""Positive pane indexing survives the measured Patchright negative-index miss."""

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.transports.migrated_composer import (
    OVERLAY,
    RADIOGROUP,
    READY_ANCHOR,
    MigratedComposer,
)
from gflow_cli.errors import UiSelectorDriftError


def pane_fixture(count):
    group = MagicMock()
    group.first = group
    group.wait_for = AsyncMock()
    selected = MagicMock()
    selected.locator.return_value = group
    missing_group = MagicMock()
    missing_group.first = missing_group
    missing_group.wait_for = AsyncMock(side_effect=PlaywrightTimeoutError("negative-index miss"))
    missing = MagicMock()
    missing.locator.return_value = missing_group
    panes = MagicMock()
    panes.filter.return_value = panes
    panes.first = selected
    panes.last = missing
    panes.count = AsyncMock(return_value=count)

    def nth(index):
        assert index >= 0, "No negative settings pane index may escape"
        return selected

    panes.nth.side_effect = nth
    trigger = MagicMock()
    trigger.first = trigger
    trigger.wait_for = AsyncMock()
    page = MagicMock()
    page.locator.side_effect = lambda selector: trigger if selector == READY_ANCHOR else panes
    composer = MigratedComposer()
    composer._dismiss_cookie_bar = AsyncMock()
    composer._dismiss_dialog = AsyncMock()
    composer._click = AsyncMock()
    composer._ui_failure_detail = AsyncMock(return_value="Settings pane index unresolved")
    return composer, page, panes, selected


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_matching_pane_uses_current_last_positive_index_when_negative_index_misses(count):
    composer, page, panes, selected = pane_fixture(count)
    result = await composer._open_pane(page)  # noqa: SLF001
    assert result is selected
    panes.nth.assert_called_once_with(count - 1)
    selected.locator.return_value.wait_for.assert_awaited()
    assert composer._click.await_count == 1


@pytest.mark.asyncio
async def test_pane_removed_after_group_wait_refuses_without_a_negative_index():
    composer, page, panes, selected = pane_fixture(0)
    with pytest.raises(UiSelectorDriftError, match="index unresolved"):
        await composer._open_pane(page)  # noqa: SLF001
    panes.nth.assert_not_called()


def captured_groups():
    # Root measured three groups/eleven radios: mode2, image aspects5, count4.
    return (
        '<div role="radiogroup"><button role="radio"><mat-icon>image</mat-icon>Image</button>'
        '<button role="radio"><mat-icon>videocam</mat-icon>Video</button></div>'
        '<div role="radiogroup">'
        + "".join(
            f'<button role="radio"><mat-icon>{icon}</mat-icon>{ratio}</button>'
            for icon, ratio in (
                ("crop_16_9", "16:9"),
                ("crop_landscape", "4:3"),
                ("crop_square", "1:1"),
                ("crop_portrait", "3:4"),
                ("crop_9_16", "9:16"),
            )
        )
        + "</div>"
        '<div role="radiogroup">'
        + "".join(f'<button role="radio">x{count}</button>' for count in range(1, 5))
        + "</div>"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["playwright", "patchright"])
@pytest.mark.parametrize("layout", ["one-pane", "trailing-menu", "two-settings"])
async def test_real_engine_returns_populated_current_settings_pane_from_captured_dom(
    engine, layout
):
    pytest.importorskip(engine)
    module = importlib.import_module(engine + ".async_api")
    async with module.async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            # Entire browser context is isolated and cannot make any external request.
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            old = (
                '<div class="cdk-overlay-pane" data-pane="old">' + captured_groups() + "</div>"
                if layout == "two-settings"
                else ""
            )
            menu = (
                '<div class="cdk-overlay-pane" data-pane="stale-menu" style="display:none">'
                '<button role="menuitem">Detached model</button></div>'
                if layout == "trailing-menu"
                else ""
            )
            await page.set_content(
                """<button class="settings-trigger-button"
                   onclick="document.getElementById('current').style.display='block'">
                   Settings</button>"""
                + old
                + '<div id="current" class="cdk-overlay-pane" data-pane="current"'
                ' style="display:none">' + captured_groups() + "</div>" + menu
            )
            pane = await MigratedComposer()._open_pane(page)  # noqa: SLF001
            assert await pane.count() == 1
            assert await pane.get_attribute("data-pane") == "current"
            assert await pane.locator(RADIOGROUP).count() == 3
            assert await pane.locator('[role="radio"]').count() == 11
            assert await pane.is_visible()
            assert await page.locator(OVERLAY).count() == (1 if layout == "one-pane" else 2)
        finally:
            await browser.close()
