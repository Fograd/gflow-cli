# Stop pre-minting image reCAPTCHA for the UI transport (#891) — Implementation Plan

> **For agentic workers:** Run `/gflow:status --feature 891-warm-client-premint` to find the next
> unchecked task. Implement one task at a time. Run `/gflow:check` before every commit.

**Goal:** An unported image form never ends as a misleading `RecaptchaError`. On an account
served flow.google.com it is refused as `FlowHostMigratedError` (exit 36), naming the form, on a
fresh or warm client.

**Architecture:** `FlowApiClient._drive_images_generation` stops pre-minting whenever the transport
declares `uses_page_owned_image_recaptcha`. Only `UiAutomationTransport` does, and neither it nor
its drivers ever read `request.recaptcha_token`: Flow's page mints its own on click. The URL and
latch logic inside that capability existed only to feed the mint decision, so it collapses to a
constant, and the client no longer imports `migrated_images_prefer`. Routing
(`_generate_images_locked`) and the experimental HTTP transports are unchanged.

**Predict verdict:** CAUTION 7/10 (posted on #891, 2026-09-29), narrowed by SCENARIO.md: the latched-client
reroute (predict design step 2) is dropped because no shipped surface reaches it.

**Risk register:**

| Severity | Risk | Mitigation |
|---|---|---|
| Medium | An account served labs relies on the client token after all | Grep proof: no reader in `ui_automation.py`, `drivers/`, `migrated_composer.py`. The labs arm cannot be observed here (308 on every profile), so record it, don't claim it |
| Medium | A fresh client whose page is still the labs bootstrap takes the labs detour before exit 36 | Same as today: the old mint did not bail there either (it minted, then the transport ran). Covered by e2e #3 |
| Low | Merge conflict with #882 (`_mint_recaptcha_token`) and #824 (`run_images`) | Neither function body changes |

---

## File structure

### Modified files
```
src/gflow_cli/api/client.py
  _drive_images_generation: skip the mint when the transport owns its page; drop the
  migrated_images_prefer import; update the #673 comment in _mint_recaptcha_token.
src/gflow_cli/api/transports/ui_automation.py
  uses_page_owned_image_recaptcha: return True; delete the URL/latch logic that only fed the mint.
src/gflow_cli/api/transports/migrated_composer.py
  migrated_images_prefer docstring: drop "the mint decision calls it" and the mint rationale.
tests/api/test_image_capability_and_cookie_bar.py
  replace test_drive_mints_when_request_is_not_migrated_servable; fix the project-less test.
tests/api/transports/test_migrated_images.py
  drop the URL-branch tests of the capability (:274-356); keep the routing tests.
tests/e2e/test_migrated_host_e2e.py
  e2e #3 (fresh client, unported model) and #4 (warm client).
scripts/dev/spike_mint_on_about_blank.py, scripts/dev/spike_warm_client_unported_form.py
  committed as the #891 evidence.
docs/superpowers/spikes/2026-09-20-warm-client-premint-on-about-blank.md
  verdict doc.
KNOWN_ISSUES.md, CHANGELOG.md
```

---

## Task 1 — Red tests
**What:** Pin the new contract before touching `src/`.
**Steps:**
- [ ] Replace `test_drive_mints_when_request_is_not_migrated_servable` with `test_drive_never_mints_for_a_page_owning_transport`: unported request (`reference_entities`), and the mint must not be awaited.
- [ ] Rewrite `test_migrated_images_prefer_keeps_project_less_runs_on_labs` so it asserts the predicate as routing uses it (`page_url` given), not the unreachable `project_id=None` client call.
**Tests created (red):**
- [ ] `test_drive_never_mints_for_a_page_owning_transport` fails on `develop`.

## Task 2 — Client + capability
**Steps:**
- [ ] `_drive_images_generation`: `if callable(getattr(self.transport, "uses_page_owned_image_recaptcha", None))` → no mint.
- [ ] `UiAutomationTransport.uses_page_owned_image_recaptcha` → `return True`, with a docstring naming the fact (the token is never read). Delete the URL/latch body.
- [ ] Delete the capability's URL-branch tests in `test_migrated_images.py`; keep `test_client_keeps_legacy_mint_for_other_image_transports`.
- [ ] Fix the `migrated_images_prefer` docstring and the `_mint_recaptcha_token` #673 comment.
**Tests:** Task 1 green; `tests/api`, `tests/features` green.

## Task 3 — E2E (Iron Law)
- [ ] #3: fresh client, `--model imagen4` on a served-flow.google.com profile → exit 36, $0.
- [ ] #4: warm client, one t2i then `imagen4` → exit 36 (ports the spike). One image of the daily cap.
- [ ] MCP twin of #3 via `gflow_generate_image`, or record the reason with evidence.
- [ ] Run on `ffroliva`, and paste the result into the PR.

## Task 4 — Evidence + docs
- [ ] Commit the two spike scripts and a spike verdict doc.
- [ ] Add the #891 line under KNOWN_ISSUES #673.
- [ ] CHANGELOG `### Fixed`.
- [ ] File the deferred issues listed in SCENARIO.md.

## Task 5 — Gates
- [ ] `/gflow:check` green, then PR → `/gflow:pr-council-review`.

---

## Definition of done
- [ ] All tasks checked; e2e #3 and #4 pasted in the PR; deferred issues filed; Closes #891.
