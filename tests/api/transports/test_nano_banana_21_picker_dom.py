"""Production legacy selectors evaluated in an isolated browser, without Flow traffic."""

import pytest

from gflow_cli.api.image import Model
from gflow_cli.api.transports.ui_automation import IMAGE_MODEL_OPTION_SELECTORS


@pytest.mark.asyncio
async def test_legacy_picker_separates_two_from_two_point_one_and_lite(page):
    await page.route("**/*", lambda route: route.abort())
    await page.set_content(
        '<div role="menu">'
        '<div role="menuitem" id="beluga">🍌\nNano Banana 2.1</div>'
        '<div role="menuitem" id="narwhal">🍌\nNano Banana 2</div>'
        '<div role="menuitem" id="lite">🍌\nNano Banana 2 Lite</div>'
        "</div>"
    )
    for model, expected in (
        (Model.NARWHAL, "narwhal"),
        (Model.BELUGA, "beluga"),
        (Model.HARBOR_SEAL, "lite"),
    ):
        selected = page.locator(IMAGE_MODEL_OPTION_SELECTORS[model][0])
        assert await selected.count() == 1
        assert await selected.get_attribute("id") == expected
