"""Fresh image menu observations never authorize paid submissions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports import migrated_upscale as transport
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


class Item:
    def __init__(self, text, disabled=False, visible=True):
        self.text, self.disabled, self.visible = text, disabled, visible
        self.click = AsyncMock()

    async def inner_text(self):
        return self.text

    async def is_visible(self):
        return self.visible

    async def is_disabled(self):
        return self.disabled

    async def get_attribute(self, name):
        return "true" if self.disabled else None


class Menu:
    def __init__(self, items):
        self.items = items
        self.visible = False

    async def query_selector_all(self, selector):
        return self.items

    async def is_visible(self):
        return self.visible


class Page:
    def __init__(self, items):
        self.menu = Menu(items)
        self.download = Item("download")
        self.download.click = AsyncMock(side_effect=self.open_menu)
        self.url = ""
        self.keyboard = SimpleNamespace(press=AsyncMock())
        self.wait_for_timeout = AsyncMock()

    async def open_menu(self):
        self.menu.visible = True

    async def goto(self, url, **kwargs):
        self.url = url

    async def wait_for_selector(self, selector, **kwargs):
        return self.download if "download" in selector else self.menu

    async def query_selector_all(self, selector):
        return [self.download] if "download" in selector else [self.menu]


async def read(monkeypatch, page, kind="image"):
    monkeypatch.setattr(
        transport,
        "lookup_asset",
        AsyncMock(
            return_value=SimpleNamespace(
                project_id=P, media_id=M, kind=kind, url="https://private.invalid"
            )
        ),
    )
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=AsyncMock())
    # The production checkin method is synchronous.
    returned = []
    client._checkin_page = lambda p: returned.append(p)
    result = await FlowApiClient.get_image_upscale_capabilities(client, project_id=P, media_id=M)
    assert returned == [page]
    return result


@pytest.mark.asyncio
async def test_enabled_and_disabled_are_independent_and_url_free(monkeypatch):
    two, four = Item("2K"), Item("4K", disabled=True)
    page = Page([two, four])
    result = await read(monkeypatch, page)
    assert [(r["resolution"], r["status"], r["available"]) for r in result["capabilities"]] == [
        ("2k", "available", True),
        ("4k", "disabled", False),
    ]
    assert result["project_id"] == P and result["media_id"] == M
    assert "private" not in str(result) and "url" not in str(result)
    page.download.click.assert_awaited_once()
    two.click.assert_not_awaited()
    four.click.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items,reason",
    [
        ([Item("2K")], "resolution_unobserved"),
        ([Item("2K"), Item("4K", visible=False)], "resolution_unobserved"),
        ([Item("2K"), Item("4K"), Item("4K", disabled=True)], "resolution_ambiguous"),
    ],
)
async def test_missing_hidden_duplicate_targets_are_unknown(monkeypatch, items, reason):
    result = await read(monkeypatch, Page(items))
    row = result["capabilities"][1]
    assert row == {"resolution": "4k", "status": "unknown", "available": None, "reason": reason}


@pytest.mark.asyncio
async def test_wrong_media_type_fails_before_detail_navigation(monkeypatch):
    page = Page([])
    with pytest.raises(ConfigurationError):
        await read(monkeypatch, page, kind="video")
    assert "/edit/" not in page.url
    page.download.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_ids_do_not_checkout():
    client = SimpleNamespace(_checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await FlowApiClient.get_image_upscale_capabilities(client, project_id="invalid", media_id=M)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_menu_does_not_publish_available(monkeypatch):
    page = Page([Item("2K"), Item("4K")])
    original = page.query_selector_all

    async def query(selector):
        if selector == '[role="menu"]':
            extra = Menu([Item("4K")])
            extra.visible = page.menu.visible
            return [page.menu, extra]
        return await original(selector)

    page.query_selector_all = query
    result = await read(monkeypatch, page)
    assert all(
        r["available"] is None and r["reason"] == "menu_ambiguous" for r in result["capabilities"]
    )


@pytest.mark.asyncio
async def test_redirected_detail_is_unknown_without_menu_click(monkeypatch):
    page = Page([Item("2K"), Item("4K")])

    async def goto(url, **kwargs):
        page.url = url if "/edit/" not in url else "https://accounts.google.com/"

    page.goto = goto
    result = await read(monkeypatch, page)
    assert all(r["reason"] == "detail_context_unverified" for r in result["capabilities"])
    page.download.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_selected_engine_selector_timeout_is_unknown(monkeypatch):
    class SelectedTimeoutError(Exception):
        pass

    monkeypatch.setattr(transport, "engine_timeout_errors", lambda: (SelectedTimeoutError,))
    page = Page([Item("2K")])

    async def timeout(selector, **kwargs):
        if selector == '[role="menu"]':
            raise SelectedTimeoutError("Private request details must never escape")
        return page.download

    page.wait_for_selector = timeout
    result = await read(monkeypatch, page)
    assert all(
        r["available"] is None and r["reason"] == "observation_timeout"
        for r in result["capabilities"]
    )
    assert "Private" not in str(result)


@pytest.mark.asyncio
async def test_cancellation_returns_page_exactly_once(monkeypatch):
    import asyncio

    page = Page([])
    entered = asyncio.Event()

    async def lookup(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(transport, "lookup_asset", lookup)
    returned = []
    client = SimpleNamespace(
        _checkout_page=AsyncMock(return_value=page), _checkin_page=returned.append
    )
    task = asyncio.create_task(
        FlowApiClient.get_image_upscale_capabilities(client, project_id=P, media_id=M)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert returned == [page]
    page.download.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_paid_menu_uses_selected_engine_typed_missing_refusal(monkeypatch):
    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.errors import UiSelectorDriftError

    class SelectedTimeoutError(Exception):
        pass

    monkeypatch.setattr(transport, "engine_timeout_errors", lambda: (SelectedTimeoutError,))
    page = Page([])

    async def wait(selector, **kwargs):
        if "download" in selector:
            return page.download
        raise SelectedTimeoutError("Sensitive URL must remain private")

    page.wait_for_selector = wait
    with pytest.raises(UiSelectorDriftError):
        await transport._upscale_menu(page, TargetResolution.RES_4K)


def test_selected_patchright_timeout_class_is_normalized(monkeypatch):
    from gflow_cli.api import _engine

    class SelectedTimeoutError(Exception):
        pass

    monkeypatch.setattr(
        _engine.importlib,
        "import_module",
        lambda name: SimpleNamespace(TimeoutError=SelectedTimeoutError),
    )
    assert SelectedTimeoutError in _engine.engine_timeout_errors("patchright")


@pytest.mark.asyncio
async def test_preexisting_menu_cannot_supply_fresh_download_evidence(monkeypatch):
    page = Page([Item("2K"), Item("4K")])
    page.menu.visible = True
    result = await read(monkeypatch, page)
    assert all(
        r["available"] is None and r["reason"] == "menu_context_unverified"
        for r in result["capabilities"]
    )
    page.download.click.assert_not_awaited()
