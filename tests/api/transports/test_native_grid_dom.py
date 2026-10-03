"""Real offline DOM proves identity joins/restoration without any account/network."""

import pytest

from gflow_cli.api.image import ImageRef
from gflow_cli.api.transports.migrated_composer import _GRID_DISCOVERY_JS, MigratedComposer
from gflow_cli.errors import ReferenceNotFoundError

FIRST = "00000000-0000-4000-8000-000000000001"
SECOND = "00000000-0000-4000-8000-000000000002"
URL = "https://flow.google.com/project/00000000-0000-4000-8000-000000000003"


async def fixture_html(page, body, url=URL):
    async def route(request):
        if request.request.resource_type == "document":
            await request.fulfill(body=body, content_type="text/html")
        else:
            await request.abort()

    await page.route("**/*", route)
    await page.goto(url)


@pytest.mark.asyncio
async def test_real_virtualized_targets_collected_across_windows_and_restored(page):
    await fixture_html(
        page,
        f'''<div id=g style="height:200px;overflow-y:auto">
      <div style="height:2000px"><img data-media-id="{SECOND}" src="/asb/recent"></div></div>
      <script>g.addEventListener('scroll',()=>{{
        g.querySelectorAll('img').forEach(e=>e.remove());
        const e=document.createElement('img');
        e.dataset.mediaId=g.scrollTop>500?'{FIRST}':'{SECOND}';
        e.src=g.scrollTop>500?'/asb/older':'/asb/recent';g.firstElementChild.append(e);
      }});</script>''',
    )
    result = await MigratedComposer().await_existing_references(
        page, (ImageRef(FIRST), ImageRef(SECOND))
    )
    assert result == {FIRST: "older", SECOND: "recent"}
    assert await page.locator("#g").evaluate("e=>e.scrollTop") == 0
    assert (
        await page.evaluate("Object.keys(window).filter(k=>k.startsWith('__gflow_grid_')).length")
        == 0
    )


@pytest.mark.asyncio
async def test_real_delayed_container_mount_is_discovered(page):
    await fixture_html(
        page,
        f'''<script>setTimeout(()=>{{document.body.innerHTML=
      '<div style="height:200px;overflow-y:auto"><div style="height:1000px">'
      +'<img data-media-id="{FIRST}" src="/asb/late"></div></div>';}},100)</script>''',
    )
    assert await MigratedComposer().await_existing_references(page, (ImageRef(FIRST),)) == {
        FIRST: "late"
    }


@pytest.mark.asyncio
async def test_real_duplicate_media_elements_refuse(page):
    await fixture_html(
        page,
        f'<img data-media-id="{FIRST}" src="/asb/a"><img data-media-id="{FIRST}" src="/asb/b">',
    )
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(FIRST),))


@pytest.mark.asyncio
async def test_real_same_url_reload_invalidates_document_state(page):
    await fixture_html(page, f'<img data-media-id="{FIRST}" src="/asb/a">')
    args = {"key": "__gflow_grid_test", "action": "begin", "ids": [FIRST]}
    assert (await page.evaluate(_GRID_DISCOVERY_JS, args))["valid"]
    await page.reload()
    args["action"] = "scan"
    assert (await page.evaluate(_GRID_DISCOVERY_JS, args))["valid"] is False


@pytest.mark.asyncio
async def test_real_multiple_media_scroll_containers_never_pick_first(page):
    html = "".join(
        f'<div style="height:200px;overflow-y:auto"><div style="height:1000px">'
        f'<img data-media-id="{mid}" src="/asb/t{n}"></div></div>'
        for n, mid in enumerate((FIRST, SECOND))
    )
    await fixture_html(page, html)
    args = {"key": "__gflow_grid_test", "action": "begin", "ids": ["missing"]}
    result = await page.evaluate(_GRID_DISCOVERY_JS, args)
    assert result["can_scroll"] is False
    args["action"] = "restore"
    assert await page.evaluate(_GRID_DISCOVERY_JS, args)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/project/00000000-0000-4000-8000-000000000003",
        "https://flow.google.com/project/not-a-project",
        "https://flow.google.com/about",
    ],
)
async def test_real_foreign_or_invalid_document_never_returns_tokens(page, url):
    await fixture_html(page, f'<img data-media-id="{FIRST}" src="/asb/a">', url=url)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().await_existing_references(page, (ImageRef(FIRST),))
