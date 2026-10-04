"""Real browser selection regression; no Google traffic or credentials."""

import asyncio

from playwright.async_api import async_playwright
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.transports.migrated_composer import MigratedComposer

scenarios("../features/native_composer_clear.feature")


@given("a real composer with ten chips and a chip-local select-all shortcut", target_fixture="case")
def case():
    return {}


@when("gflow clears the entire prompt")
def clear(case):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            try:
                page = await browser.new_page()
                chips = "".join(
                    '<span class="mention-chip" contenteditable="false"'
                    ' data-reference-type="media">reference ' + str(i) + "</span> "
                    for i in range(10)
                )
                await page.set_content(
                    '<div contenteditable="true">' + chips + "</div><script>"
                    'document.querySelector("div").addEventListener("keydown",e=>{'
                    'if(e.ctrlKey&&e.key==="a"){e.preventDefault();'
                    "const r=document.createRange();"
                    'r.selectNode(document.querySelector(".mention-chip:last-of-type"));'
                    "const s=window.getSelection();s.removeAllRanges();s.addRange(r);}});"
                    "window.inputCount=0;"
                    'document.querySelector("div").addEventListener("input",'
                    "()=>window.inputCount++);</script>"
                )
                comp = MigratedComposer()
                assert len(await comp.read_chips(page)) == 10
                await comp.clear_composer(page)
                case["remaining"] = len(await comp.read_chips(page))
                case["text"] = await page.locator('[contenteditable="true"]').inner_text()
                case["input_events"] = await page.evaluate("window.inputCount")
            finally:
                await browser.close()

    asyncio.run(run())


@then("all chips and prompt text are removed by an editing event")
def verified(case):
    assert case["remaining"] == 0
    assert case["text"].strip() == ""
    assert case["input_events"] >= 1
