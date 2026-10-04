"""Real isolated DOM exercises append caret and owned-token selection; no account traffic."""

import json

import pytest

from gflow_cli.api.image import ImageRef
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ReferenceNotFoundError

IDS = tuple(f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 11))
REFS = tuple(ImageRef(mid, display_name=f"fixture-{i}.png") for i, mid in enumerate(IDS))
TOKENS = {mid: f"owned-{i}" for i, mid in enumerate(IDS)}


async def mount_picker(page, monkeypatch, *, existing=0, duplicate=False):
    """Use the primary picker contract: boundary @, focused input, substring title search.

    A center click lands inside ordinary draft text after two media chips. DOM Range
    changes, input events and the production caret JS execute in a real browser. The
    fixture models the cached native activation/filter contract, not ProseMirror itself.
    """
    assets = [
        {"id": ref.name, "title": ref.display_name, "token": TOKENS[ref.name]} for ref in REFS
    ]
    if duplicate:
        assets.append(assets[0])
    html = r"""<div id="editor" contenteditable="true" style="width:700px;height:100px"></div>
<script>
const editor=document.getElementById('editor');
const assets=ASSETS;
function chip(asset) {
 const s=document.createElement('span');s.className='mention-chip';
 s.contentEditable='false';s.dataset.referenceType='media';s.dataset.mediaId=asset.id;
 s.textContent=asset.title;return s;
}
for (const asset of assets.slice(0, EXISTING)) editor.append(chip(asset),' ');
const anchor=document.createTextNode('anchor ');editor.append(anchor);
// Deterministic center hit on ordinary draft text: a real collapsed DOM Range.
editor.addEventListener('click',()=> {
 const r=document.createRange();r.setStart(anchor,3);r.collapse(true);
 const s=window.getSelection();s.removeAllRanges();s.addRange(r);
});
window.pickerOpens=0;window.pickerQueries=[];
editor.addEventListener('beforeinput',event=> {
 if(event.data!=='@')return;
 const s=window.getSelection();if(!s.rangeCount)return;
 const r=s.getRangeAt(0).cloneRange();
 const before=document.createRange();before.selectNodeContents(editor);
 before.setEnd(r.startContainer,r.startOffset);
 const prefix=before.toString();
 // Native Bib activates only at paragraph start/whitespace/mention boundary.
 if(prefix && !/\s/.test(prefix.at(-1)))return;
 event.preventDefault();
 const marker=document.createTextNode('@');r.insertNode(marker);
 const pane=document.createElement('flow-add-menu-popover-content');
 const input=document.createElement('input');input.type='text';pane.append(input);
 const options=document.createElement('div');pane.append(options);
 function render(){
  window.pickerQueries.push(input.value);
  options.replaceChildren();
  for(const asset of assets.filter(a=>a.title.toLowerCase().includes(input.value.toLowerCase()))) {
   const b=document.createElement('button');b.className='asset-item';b.role='option';
   const img=document.createElement('img');img.src='/asb/'+asset.token;b.append(img);
   b.dataset.mediaId=asset.id;options.append(b);
  }
 }
 input.addEventListener('input',render);
 input.addEventListener('keydown',event=> {
  if(event.key==='Escape'){pane.remove();editor.focus();return;}
  if(event.key!=='Enter')return;
  event.preventDefault();const b=options.firstElementChild;if(!b)return;
  const asset=assets.find(a=>a.id===b.dataset.mediaId);
  marker.replaceWith(chip(asset),document.createTextNode(' '));pane.remove();editor.focus();
  const end=document.createRange();end.selectNodeContents(editor);end.collapse(false);
  const selection=window.getSelection();selection.removeAllRanges();selection.addRange(end);
 });
 document.body.append(pane);window.pickerOpens++;render();input.focus();
});
</script>""".replace("ASSETS", json.dumps(assets)).replace("EXISTING", str(existing))

    async def route(request):
        if request.request.resource_type == "document":
            await request.fulfill(body=html, content_type="text/html")
        else:
            await request.abort()

    await page.route("**/*", route)
    await page.goto("https://fixture.invalid/picker")
    original_type = page.keyboard.type

    async def fast_type(text, **kwargs):
        await original_type(text, delay=0)

    async def no_wait(_):
        pass

    monkeypatch.setattr(page.keyboard, "type", fast_type)
    monkeypatch.setattr(page, "wait_for_timeout", no_wait)


@pytest.mark.asyncio
async def test_real_center_caret_misses_third_but_end_caret_opens_owned_picker(page, monkeypatch):
    await mount_picker(page, monkeypatch, existing=2)
    composer = MigratedComposer()
    third = REFS[2]
    with pytest.raises(ReferenceNotFoundError):
        await composer._mention_by_token(
            page, third.display_name, TOKENS[third.name], third.name, expect_chips=3
        )
    assert await page.evaluate("window.pickerOpens") == 0
    assert await page.locator(".mention-chip").count() == 2
    await composer._mention_by_token(
        page,
        third.display_name,
        TOKENS[third.name],
        third.name,
        expect_chips=3,
        at_end=True,
    )
    assert await page.evaluate("window.pickerOpens") == 1
    assert await page.locator(".mention-chip").evaluate_all(
        "es=>es.map(e=>e.dataset.mediaId)"
    ) == list(IDS[:3])
    assert await page.evaluate("window.pickerQueries.at(-1)") == third.display_name


@pytest.mark.asyncio
async def test_real_existing_reference_batch_appends_all_ten_in_owned_order(page, monkeypatch):
    await mount_picker(page, monkeypatch)
    assert await MigratedComposer().attach_existing_references(page, REFS, TOKENS) == IDS
    assert await page.locator(".mention-chip").evaluate_all(
        "es=>es.map(e=>e.dataset.mediaId)"
    ) == list(IDS)
    assert await page.evaluate("window.pickerOpens") == 10
    assert await page.locator("flow-add-menu-popover-content").count() == 0


@pytest.mark.asyncio
async def test_real_duplicate_owned_tokens_remain_ambiguous_with_end_caret(page, monkeypatch):
    await mount_picker(page, monkeypatch, duplicate=True)
    with pytest.raises(ReferenceNotFoundError):
        await MigratedComposer().attach_existing_references(page, REFS[:1], TOKENS)
    assert await page.locator(".mention-chip").count() == 0
    assert await page.evaluate("window.pickerOpens") == 1
