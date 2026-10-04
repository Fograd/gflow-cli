"""Newest library popover selection avoids Patchright negative-index misses."""

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.transports.migrated_composer import (
    OVERLAY,
    PICKER,
    PICKER_CONFIRM,
    PICKER_SEARCH,
    _picker_pane,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("count, expected_index", [(0, 0), (1, 0), (2, 1)])
async def test_picker_selection_uses_nonnegative_latest_index(count, expected_index):
    selected = MagicMock()
    panes = MagicMock()
    panes.filter.return_value = panes
    panes.count = AsyncMock(return_value=count)
    panes.nth.return_value = selected
    page = MagicMock()
    page.locator.return_value = panes
    result = await _picker_pane(page)
    assert result is selected
    panes.nth.assert_called_once_with(expected_index)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["playwright", "patchright"])
@pytest.mark.parametrize("layout", ["one-picker", "hidden-old-picker"])
async def test_real_engine_newest_picker_stays_visible_until_confirm_then_hidden(engine, layout):
    pytest.importorskip(engine)
    module = importlib.import_module(engine + ".async_api")
    async with module.async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            old = (
                '<div class="cdk-overlay-pane" data-pane="old" style="display:none">'
                '<flow-add-menu-popover-content><input type="text">'
                "</flow-add-menu-popover-content></div>"
                if layout == "hidden-old-picker"
                else ""
            )
            await page.set_content(
                old + '<div id="current" class="cdk-overlay-pane" data-pane="current">'
                "<flow-add-menu-popover-content>"
                '<input type="text">'
                '<button class="detail-add-to-prompt-btn" '
                "onclick=\"document.getElementById('current').style.display='none'\">"
                "Add to prompt</button></flow-add-menu-popover-content></div>"
                '<div class="cdk-overlay-pane" style="display:none">'
                '<button role="menuitem">Unrelated detached menu</button></div>'
            )
            picker = await _picker_pane(page)
            assert await picker.count() == 1
            assert await picker.get_attribute("data-pane") == "current"
            assert await picker.locator(PICKER_SEARCH).count() == 1
            assert await picker.is_visible()
            # A stale hidden first pane must never make commit seem complete.
            with pytest.raises(module.TimeoutError):
                await picker.wait_for(state="hidden", timeout=100)
            confirm = (await _picker_pane(page)).locator(PICKER_CONFIRM).first
            assert await confirm.is_visible()
            await confirm.click()
            await (await _picker_pane(page)).wait_for(state="hidden", timeout=1000)
            assert await page.locator(OVERLAY).filter(has=page.locator(PICKER)).count() == (
                1 if layout == "one-picker" else 2
            )
        finally:
            await browser.close()
