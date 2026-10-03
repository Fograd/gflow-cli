"""#799's agent-only cohort, discriminated against a real CSS engine.

The whole fix turns on one piece of third-party behaviour: whether Playwright reports
a `<button hidden="">` as present-but-not-visible. If it reported it visible, the
readiness gate would never have failed and none of this code would run; if it reported
it absent, the guard would fall through to selector drift and #799 would be unchanged.
A fake answers whatever it was written to answer, so it cannot settle that — only a
real browser can, and AGENTS.md asks for exactly this before wiring in an assumption
about someone else's runtime.

Provenance, precisely: the reporter's issue posts an elided `<button hidden="" ...
aria-label="Settings trigger" class="... settings-trigger-button ...">`, and those
attributes are theirs verbatim. The surrounding component chain
(`flow-creative-agent-prompt-box`, `agent-footer-actions`) comes from the #749 spike
that measured this host. That is not circular — neither selector under test touches
any of it; only the `hidden` attribute and the two class names are load-bearing.

What this does NOT prove is that Flow still serves it; that needs an account in that
cohort, which is a named external blocker on #799. It proves the discriminator is
sound on the DOM we were given, and that its negative controls do not fire.

Two of those controls were also measured against LIVE Flow at $0 (council D6), since
synthetic markup is not the live arm:

* healthy migrated composer (`ffroliva`, a real project page) — trigger present and
  visible, `button.agent-mode-chip` present and **un-pressed**, verdict `False`. This
  is the load-bearing one: a normal account on this host HAS a chip, so having none
  is genuinely anomalous rather than merely unmatched.
* live `/about` landing (`denon82`, #756) — trigger absent, verdict `False`, i.e. the
  `TRIGGER_GONE` arm reached on a real page rather than a written one.

No account, no network, no credits; skips when Chromium is absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gflow_cli.api.transports.migrated_composer import MigratedComposer

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Page

#: The composer as #799 captured it: the trigger is in the page under a bare `hidden`,
#: and there is no agent-mode chip anywhere, because this account has no classic arm.
AGENT_ONLY = """
<flow-creative-agent-prompt-box>
  <button hidden="" aria-label="Settings trigger"
          class="mat-mdc-icon-button settings-trigger-button flow-icon-button-transparent">
    <mat-icon class="google-symbols">tune</mat-icon>
  </button>
  <div class="agent-footer-actions"><button class="agent-action-button">Settings</button></div>
</flow-creative-agent-prompt-box>
"""

#: #749's recoverable arm: same hidden trigger, but a chip exists to turn off. The
#: recovery owns this, and the guard must keep its hands off it.
AGENT_MODE_RECOVERABLE = """
<flow-creative-agent-prompt-box>
  <button hidden="" aria-label="Settings trigger" class="settings-trigger-button"></button>
  <button class="agent-mode-chip" aria-pressed="true">
    <span class="agent-mode-chip-label">Agent</span>
  </button>
</flow-creative-agent-prompt-box>
"""

#: Ordinary drift: the anchor is gone from the DOM entirely. Our bug, not a cohort.
TRIGGER_GONE = """
<flow-prompt-box><button class="some-renamed-button"></button></flow-prompt-box>
"""

#: A healthy classic composer — the trigger is right there and visible.
HEALTHY = """
<flow-prompt-box>
  <button aria-label="Settings trigger" class="settings-trigger-button">tune</button>
</flow-prompt-box>
"""


async def _verdict(page: Page, markup: str) -> bool:
    from gflow_cli.api.transports.migrated_composer import READY_ANCHOR

    await page.set_content(markup)
    trigger = page.locator(READY_ANCHOR).first
    return await MigratedComposer._is_agent_only_composer(page, trigger)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_a_bare_hidden_attribute_really_does_read_as_present_but_invisible(
    page: Page,
) -> None:
    """The load-bearing third-party assumption, measured rather than assumed."""
    from gflow_cli.api.transports.migrated_composer import READY_ANCHOR

    await page.set_content(AGENT_ONLY)
    trigger = page.locator(READY_ANCHOR).first

    assert await trigger.count() == 1, "the reporter's class list must still match"
    assert await trigger.is_visible() is False, "a bare `hidden` must not read as visible"


@pytest.mark.asyncio
async def test_the_reporters_captured_composer_is_recognised(page: Page) -> None:
    assert await _verdict(page, AGENT_ONLY) is True


@pytest.mark.asyncio
async def test_the_recoverable_agent_mode_is_left_to_its_recovery(page: Page) -> None:
    """A chip in the page means there IS a classic arm — #749 owns this, not #799."""
    assert await _verdict(page, AGENT_MODE_RECOVERABLE) is False


@pytest.mark.asyncio
async def test_a_vanished_trigger_stays_selector_drift(page: Page) -> None:
    assert await _verdict(page, TRIGGER_GONE) is False


@pytest.mark.asyncio
async def test_a_healthy_composer_is_never_called_a_cohort(page: Page) -> None:
    assert await _verdict(page, HEALTHY) is False


@pytest.mark.asyncio
async def test_expanded_panel_reveals_pressed_chip_before_recovery(page: Page) -> None:
    """Measured R01: expanded chat removes the chip; close remounts it."""
    await page.set_content("""
      <button hidden class="settings-trigger-button">settings</button>
      <flow-agent-panel><button class="header-action" onclick="
        this.parentElement.remove();
        const chip=document.createElement('button');
        chip.className='agent-mode-chip'; chip.setAttribute('aria-pressed','true');
        chip.onclick=()=>{chip.setAttribute('aria-pressed','false');
          document.querySelector('.settings-trigger-button').hidden=false};
        document.body.appendChild(chip);
      "><mat-icon>close</mat-icon></button></flow-agent-panel>
    """)
    assert await page.locator("button.agent-mode-chip").count() == 0
    state, error = await MigratedComposer._exit_agent_mode(page)
    assert (state, error) == ("clicked", None)
    assert await page.locator(".settings-trigger-button").is_visible()


@pytest.mark.asyncio
@pytest.mark.parametrize("pressed", ["false", None])
async def test_panel_recovery_does_not_enable_agent_mode(page: Page, pressed: str | None) -> None:
    value = (
        ""
        if pressed is None
        else (
            "<button class='agent-mode-chip' aria-pressed='false' onclick='window.flipped=true'>"
            "</button>"
        )
    )
    await page.set_content("""
      <flow-agent-panel>
        <button class="header-action"><mat-icon>close</mat-icon></button>
      </flow-agent-panel>
    """)
    await page.locator("button.header-action").evaluate(
        "(e, markup)=>e.onclick=()=>{e.parentElement.remove();"
        "document.body.insertAdjacentHTML('beforeend',markup)}",
        value,
    )
    state, error = await MigratedComposer._exit_agent_mode(page)
    assert (state, error) == ("absent", None)
    assert await page.evaluate("Boolean(window.flipped)") is False


@pytest.mark.asyncio
async def test_ambiguous_panel_close_does_not_mutate(page: Page) -> None:
    await page.set_content("""
      <flow-agent-panel>
        <button class="header-action" onclick="window.clicked=true">
          <mat-icon>close</mat-icon>
        </button>
        <button class="header-action" onclick="window.clicked=true">
          <mat-icon>close</mat-icon>
        </button>
      </flow-agent-panel>
    """)
    state, error = await MigratedComposer._exit_agent_mode(page)
    assert (state, error) == ("absent", None)
    assert await page.evaluate("Boolean(window.clicked)") is False
