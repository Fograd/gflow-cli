"""Real virtualized picker DOM; browser events establish the selected exact token."""

import json

import pytest

from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ReferenceNotFoundError


async def virtual_picker(page, monkeypatch, *, duplicate=False, confirm=True):
    assets = [{"id": str(i), "token": f"owned-{i}"} for i in range(100)]
    if duplicate:
        assets[65]["token"] = "owned-64"
    html = r"""<div contenteditable="true" style="width:700px;height:100px"></div>
<script>
const assets=ASSETS,editor=document.querySelector('[contenteditable]');
window.optionClicks=0;window.confirmClicks=0;
editor.addEventListener('beforeinput',event=>{
 if(event.data!=='@')return;event.preventDefault();
 const pane=document.createElement('flow-add-menu-popover-content');
 const input=document.createElement('input');input.type='text';
 const view=document.createElement('cdk-virtual-scroll-viewport');
 view.className='asset-list-viewport';view.style='display:block;height:120px;overflow-y:auto;position:relative';
 const content=document.createElement('div');
 content.style='height:2000px;position:relative';view.append(content);
 let selected=null;
 const confirm=document.createElement('button');confirm.className='detail-add-to-prompt-btn';
 confirm.textContent='Commit';
 confirm.onclick=()=>{if(!selected)return;window.confirmClicks++;
  const chip=document.createElement('span');
  chip.className='mention-chip';chip.contentEditable='false';
  chip.dataset.referenceType='media';chip.dataset.mediaId=selected.id;editor.append(chip);
  pane.remove();editor.focus();};
 function render(){
  content.replaceChildren();
  window.renderedScrollTop=view.scrollTop;
  const start=Math.floor(view.scrollTop/20);
  for(const asset of assets.slice(start,start+10)){
   const button=document.createElement('button');button.className='asset-item';button.role='option';
   if(selected?.id===asset.id)button.classList.add('asset-item-active');
   button.style='position:absolute;top:'+(Number(asset.id)*20)+'px;height:20px';
   const img=document.createElement('img');img.src='/asb/'+asset.token;button.append(img);
   button.onclick=()=>{window.optionClicks++;selected=asset;
    for(const b of content.children)b.classList.remove('asset-item-active');
    button.classList.add('asset-item-active');};
   content.append(button);
  }
 }
 view.addEventListener('scroll',render);
 input.onkeydown=event=>{if(event.key==='Escape'){pane.remove();editor.focus();}};
 pane.append(input,view);if(CONFIRM)pane.append(confirm);
 document.body.append(pane);render();input.focus();
});
</script>""".replace("ASSETS", json.dumps(assets)).replace(
        "CONFIRM", "true" if confirm else "false"
    )

    async def route(route):
        if route.request.resource_type == "document":
            await route.fulfill(body=html, content_type="text/html")
        else:
            await route.abort()

    await page.route("**/*", route)
    await page.goto("https://fixture.invalid/virtualized-picker")
    original_type = page.keyboard.type

    async def fast_type(text, **kwargs):
        await original_type(text, delay=0)

    async def short_wait(_):
        await page.wait_for_function(
            """()=>{const v=document.querySelector(
                'cdk-virtual-scroll-viewport.asset-list-viewport');
                return !v || window.renderedScrollTop===v.scrollTop;}""",
            timeout=5000,
        )

    monkeypatch.setattr(page.keyboard, "type", fast_type)
    monkeypatch.setattr(page, "wait_for_timeout", short_wait)


@pytest.mark.asyncio
async def test_older_exact_token_scrolls_selects_and_confirms(page, monkeypatch):
    await virtual_picker(page, monkeypatch)
    await MigratedComposer()._mention_by_token(
        page, "shared", "owned-64", "64", expect_chips=1, at_end=True
    )
    assert await page.locator(".mention-chip").evaluate_all("es=>es.map(e=>e.dataset.mediaId)") == [
        "64"
    ]
    assert await page.evaluate("window.optionClicks") == 1
    assert await page.evaluate("window.confirmClicks") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate,confirm", [(True, True), (False, False)])
async def test_ambiguous_or_unconfirmed_scroll_target_never_commits(
    page, monkeypatch, duplicate, confirm
):
    await virtual_picker(page, monkeypatch, duplicate=duplicate, confirm=confirm)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer()._mention_by_token(
            page, "shared", "owned-64", "64", expect_chips=1, at_end=True
        )
    assert await page.locator(".mention-chip").count() == 0
    assert await page.evaluate("window.confirmClicks") == 0
