# Spike — what a reCAPTCHA mint failure looks like, and whether it is transient (#915)

**Date:** 2026-10-01 · **Profile:** `ci-probe` (host Flow served: flow.google.com) ·
**Cost:** $0 (mints only, tokens discarded) ·
**Script:** [`scripts/dev/spike_recaptcha_error_shape.py`](../../../scripts/dev/spike_recaptcha_error_shape.py)

## Question

`RecaptchaError` subclasses `RuntimeError`, not `GFlowError` (#915), so it exits 1 with no
Problem Details and aborts a batch past `--continue-on-error`. Making it a `GFlowError`
needs one answer the code cannot give: **is it retryable?** A retry flag that invites a
doomed loop is worse than none (`FlowHostMigratedError`, #639).

## Where it can be raised (code, not live)

`TokenMinter` (`api/recaptcha.py`) is the only raiser, reached only through
`FlowApiClient._mint_recaptcha_token`, whose callers are:

- `extend_video` (`gflow video extend`)
- `_upsample_image_impl` (`gflow image upscale`)
- image generation on a transport **without** `uses_page_owned_image_recaptcha` — the
  experimental HTTP transports. The default `ui_automation` transport skips the client
  mint since #891, so `gflow image t2i` / `image batch` / `gflow run` on the default
  transport never raise it.

No MCP tool exposes upscale or extend on `develop`; the worker reaches it only on an
experimental transport.

## Measurements (one run, real page pool)

| Arm | Path | Result |
|---|---|---|
| A. pool page at `about:blank` (#891/#914 state) | client `_mint_recaptcha_token` ×3 | `RecaptchaError` "Could not discover reCAPTCHA site key…" **3/3, identical** |
| B. flow.google.com root grid | client path | `FlowHostMigratedError` (exit 36) — guarded before the mint |
| C. flow.google.com `/project/<id>`, steady | `TokenMinter.mint` ×5 | **5/5 OK** (≈2.4k-char tokens) |
| D. mint racing a navigation on that page | `TokenMinter.mint`, then re-mint after settle, ×3 | raced: `RecaptchaError` "evaluate failed … Execution context was destroyed" **3/3**; re-mint **3/3 OK** |

## Reading (pre-registered in the script)

- **Missing site key is deterministic for the page it ran on** (A). Re-asking the same
  page fails the same way; the cause is the page state, not timing. → `retryable=False`.
- **An execute failure is a page-state race that clears** (D). The same page mints once it
  settles. → `retryable=True`.
- A healthy project page does not fail (C), so there is no evidence of a background
  flake rate that would make the whole class retryable.

## Not measured

- An empty token returned by `grecaptcha` (the third raise site): not produced here.
  It keeps the class default (not retryable) until it is observed — no claim is made.
- Labs-served accounts: none reachable (labs answers 308 on the three profiles here
  that hold a live Flow session).
