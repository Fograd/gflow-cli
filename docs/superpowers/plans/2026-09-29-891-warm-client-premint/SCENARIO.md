# Scenario: stop pre-minting image reCAPTCHA for the UI transport (#891)

Inputs: the predict verdict posted on #891 (2026-09-29, CAUTION 7/10), plus two corrections
found while scoping this document. Both corrections are verified against `develop` 342f39df.

## Corrections to the predict

1. **No shipped surface can reach the #891 failure today.** It needs a successful image run
   followed by an unported image form **on one `FlowApiClient`**:
   - A single `gflow image t2i` / `i2i` run opens one client for one request.
   - MCP and the worker open a client per task (`worker/daemon.py:183`).
   - Multi-prompt `t2i` (`run_image_batch`) builds every item with the same model/aspect and
     no refs (`image_batch.py:502`), so it cannot mix a ported and an unported form.
   - `gflow image batch` (manifest) goes to `generate_images_batch`, which is refused outright on
     flow.google.com (`test_image_batch_is_refused_on_the_migrated_host_before_any_submit`).
   - `gflow movie` and the services layer do not generate images.

   Only direct library use reaches it, which is what the 2026-09-20 spike did. The predict's
   "`gflow image batch` with `batch:0`" trigger is wrong: `_to_request` (`image_batch.py:882`)
   drops `ref`/`reference_entity`, so they only order the DAG. That is a separate latent bug.
2. **So design step 2 of the predict (reroute a latched client from `about:blank`) guards a path
   nothing takes.** It is dropped under YAGNI. Design step 1 alone removes the whole failure mode,
   because the UI transport never needs the client-minted token.

## Coverage map

| Dim | Active? | Why |
|---|---|---|
| D2 WAF/reCAPTCHA | yes | The change removes a `grecaptcha.execute` call |
| D5 Page pool | yes | Pool pages 1..n are never navigated; the mint used to run on them |
| D7 Exit codes | yes | An unported form must end as exit 36, never `RecaptchaError` |
| D9 Transport | yes | The experimental HTTP transports still need the token |
| D12 Observability | yes | `recaptcha_mint_failed_off_migrated_host` stops firing on the image path |
| D13 MCP | yes | `gflow_generate_image` (direct and queued) runs the same client code |
| D1, D3, D4, D6, D8, D10, D11 | no | No auth, selector, manifest, data, path, headless or input change |

## Scenario table

| # | Dim | Scenario | Severity | Expected behaviour | Test category |
|---|---|---|---|---|---|
| 1 | D9 | Experimental HTTP transport (`bearer`, `evaluate_fetch`) generates an image | **Critical** | Still mints; the token is in the request body | Unit (existing `test_client_keeps_legacy_mint_for_other_image_transports`) |
| 2 | D2 | UI transport with an **unported** form (`--model imagen4`, `-i`, UUID `--ref`, entity) | **High** | `_mint_recaptcha_token` is never awaited; the transport decides | Unit (replaces `test_drive_mints_when_request_is_not_migrated_servable`) |
| 3 | D7 | Fresh client, account served flow.google.com, unported form (the shipped CLI/MCP path) | **High** | `FlowHostMigratedError`, exit 36, form named, $0 | E2E live (`e2e_image`, $0: refused pre-submit) |
| 4 | D2 | Warm client: a successful t2i, then an unported form on the same client (the #891 repro) | **High** | Not `RecaptchaError`; ends `FlowHostMigratedError` exit 36 | E2E live (`e2e_image`, one image of the daily cap) |
| 5 | D2 | UI transport, ported request | High | Unchanged: no mint (was already skipped) | Unit (existing `test_drive_skips_mint_for_servable_request`) |
| 6 | D13 | `gflow_generate_image` with an unported form, direct and queued | High | Same exit-36 Problem Details as the CLI; no docstring or payload change | E2E live: MCP twin of #3, or record why it is the same client call |
| 7 | D2 | Account served labs, unported form, on the labs driver | Medium | Page mints its own token on click; the client token was never read | Not observable here (labs answers 308 on every profile, 2026-09-14 survey). Record, do not claim |
| 8 | D5 | `GFLOW_CLI_CONCURRENCY>1` on the UI transport | Low | No mint, so the never-navigated pool pages are no longer involved | Unit (covered by #2) |
| 9 | D12 | The image path no longer emits `recaptcha_mint_failed_off_migrated_host` | Low | The event name is unchanged (asserted by `test_client_migrated_mint.py:153` for the mint itself) | Existing test |
| 10 | — | `migrated_images_prefer` project-less claim (#891 point 2) | Medium | The test asserts a shape production can produce; the CHANGELOG is corrected | Unit |

## Must-cover before merge
- #1, #2, #5: offline.
- #3, #4: e2e. `tests/e2e/test_migrated_host_e2e.py` is the home; #4 ports `scripts/dev/spike_warm_client_unported_form.py`.
- #6: run the MCP twin, or record that the change sits below both adapters and the adapter is untouched. Iron Law: prefer the run.
- #10.

## Deferred (file as issues)
- **Batch rows drop `ref`/`reference_entity`** (`image_batch.py:_to_request`, `:502`). References only order the DAG.
- **`upscale_image` / `extend_video` mint on the pool page** (`client.py:2547`, `:2268`) and genuinely need the token. On a warm client parked at `about:blank` they should hit the same `RecaptchaError`. Inferred, not run: needs a spike.
- **`RecaptchaError` is a `RuntimeError`, not a `GFlowError`** (`recaptcha.py:25`), so it aborts a batch and ignores `--continue-on-error`.
- **The misleading "Still reads as labs" branch on `about:blank`.** Wait for #882, which rewrites `_mint_recaptcha_token`.

## Suggested BDD scenarios

```gherkin
@e2e @e2e_image
Feature: an unported image form on flow.google.com is refused by name
  Scenario: warm client after a successful image
    Given a client that has generated one image on flow.google.com
    When the same client is asked for an image with an unported model
    Then it fails with FlowHostMigratedError naming the model
    And no reCAPTCHA token was minted by the client
```

## Known-issues cross-reference
- **KNOWN_ISSUES #673** (`RecaptchaError` on a moved account): resolved for the warm-client shape by this change. Add the #891 line, worded as "on an account served flow.google.com".
- **#692** (handoff race during the mint): the image path no longer mints, so its race no longer applies to images. The experimental HTTP transports and video/upscale keep the guard.
