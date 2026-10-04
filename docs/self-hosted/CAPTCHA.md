# CAPTCHA providers and supplied tokens

The normal image path uses Google's browser-owned token. Provider configuration is
optional. Adding a key does not silently change the default generation path.

## Configuration

Authenticated `POST /v1/google-flow/accounts/captcha-providers` accepts only
`CapSolver` and `2Captcha` string keys. An empty string removes that key. GET on
the same path returns `***configured***`, never the key. The implementation
atomically updates only `GFLOW_CAPSOLVER_KEY` and `GFLOW_2CAPTCHA_KEY` in the
service user's `~/.config/homelab/secrets.env`, retaining other lines and mode 600.
Only ordinary alphanumeric, underscore and hyphen API keys are accepted.

Use an SSH tunnel or TLS when sending secrets across an untrusted network. Avoid
putting keys directly into shell command arguments or source files.

## Image requests

`POST /images` accepts `captchaToken`: 20–20000 characters, single submission.
It is mutually exclusive with `captchaOrder` and `captchaRetry`.

Image requests accept configured captchaOrder and explicit captchaRetry1–10.
Provider metadata must come from a fresh trusted reload for the exact project,
IMAGE_GENERATION action and site key. Solve failure may select the next configured
provider before Google submission. A typed, single-frame WAF refusal permits an
explicit bounded retry with fresh token/request identities; partial, mixed,
duplicate or uncertain acknowledgements stop without replay. Supplied tokens
remain one use. Missing keys/malformed controls return422.

The supplied-token hook replaces both observed token contexts in the validated
`ogiZ0b` request. It checks project, output count and envelope shape before
submission; an unfamiliar shape aborts. Tokens never enter durable job JSON:
a private temporary file is consumed and removed by the worker. The browser still
mints its own token, then the outgoing request uses the supplied override. The
wire slots and one-shot rewrite have offline coverage, but live acceptance of an
externally supplied replacement token remains unverified. Ordinary browser-owned
image generation and native seed enforcement are independently live verified.

The provider clients below are enabled by explicit request controls. Their implementation and measured refusal paths do not prove Google acceptance.

Clients use Enterprise v3 tasks according to
[CapSolver's documentation](https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/)
and [2Captcha's documentation](https://2captcha.com/api-docs/recaptcha-v3).
A solve has a bounded deadline and creates one task. The whole provider
sequence has a deadline of 110 seconds before Google submission. A timed-out
provider task may still be charged by that provider. Redirects and environment
proxy inheritance are disabled. Provider response text and credentials are not
included in public errors. Reporting correct/incorrect task results back to the
providers is not implemented.

## Statistics and verification

Authenticated GET `/accounts/captcha-stats` returns aggregate observations from
this instance only. `accepted` requires the exact matching positive
operation acknowledgment; a token solve, configuration or submission is insufficient. `submitted` is an observed transport submission; neither a solved
token nor a configured key proves Google acceptance. The database contains no
keys, tokens or provider task bodies. Global useapi statistics and anonymised
cross-customer comparisons are not reproduced.

Provider task contracts, key preservation/masking and malformed-response paths
are tested offline. Native request token slots were observed with an aborted
request. Earlier JavaScript hooks did not capture metadata; the native reload parser supersedes that failure. Provider controls are implemented, but actual CapSolver/2Captcha replacement acceptance remains unverified. Supplied-token slot rewriting is guarded; current live evidence must be checked in VERIFICATION.md before claiming acceptance.

Acceptance is recorded from the exact matching native acknowledgement before later download/storage. A solved token alone never counts as accepted.

For a local masked key editor and credit-free balance check, see [the CapSolver GUI guide](CAPSOLVER_GUI.md). Saving a key does not automatically change generation or prove Google token acceptance.

A fresh same-page TokenMinter replacement was submitted in a live BDD but Google rejected it with unusual-activity/WAF 403. No accepted image was returned. This does not prove all external tokens fail, nor does it permit claiming a successful replacement path. Actual CapSolver acceptance still needs a successful controlled live Google test.

Actual CapSolver proof: one paid task solved, one replacement request submitted to Google, zero accepted images (`solveStarted=1`, `solved=1`, `submitted=1`, `accepted=0`). Google rejected unusual activity (gRPC 7/HTTP 403); no retry was made. Explicit provider controls are now available; the GUI capability indicator follows whether a key is configured, and does not claim Google acceptance. A provider solution is distinct from Google acceptance.

Statistics record `rejected` only for a typed Google WAF refusal during generation. Post-submission timeouts or mixed/unknown acknowledgements record unknown. An exact accepted acknowledgement stays accepted after a later download failure. These counters never trigger automatic solving or generation retries.

Native reference/edit/extension/promotion/TTS supplied-token and provider scopes are implemented;
see [exact native scope and verification](NATIVE_CAPTCHA.md). Provider-backed
Google acceptance remains unverified; image and dedicated native provider controls are available.


## Dedicated native provider controls
Native R2V, Omni edit, extension, promotion and saved-TTS creation accept exactly
one of captchaToken, captchaOrder, captchaRetry. captchaOrder is a comma-separated
unique sequence of configured CapSolver and/or 2Captcha. Solve failures may fall
back before Google submission. captchaRetry explicitly bounds 1–10 attempts;
default requests remain one attempt. Each retry obtains a fresh scoped token and
request identities. Only a typed WAF refusal plus confirmed submitted/rejected
telemetry permits another attempt. Accepted or uncertain outcomes, content/auth/
rate-limit errors, cancellation and later save/download failures stop. Supplied
tokens remain one use and never trigger retries.

Fresh trusted project-page site key discovery precedes paid solving. Keys remain
private; tokens stay outside durable jobs. Scope exit invalidates inherited async
work. Native acceptance is recorded at acknowledgement, so later download failure
does not erase acceptance or justify generation again. Image and generic count1-4
provider controls are also explicitly enabled; enabling controls is not proof of acceptance.

Three real saved-TTS previews on 4 October—two browser and one CapSolver—were explicitly
WAF-refused. The provider solved once and submitted once, with no accepted audio.
Credits stayed unchanged on refused requests; successful audio cost is unproven.

## Local event filters
GET /accounts/captcha-stats accepts date=YYYY-MM-DD, limit=1..50000 and
provider=CapSolver|2Captcha|UserProvided. Default date is today UTC; an explicit
limit selects latest events independently of date. Events are local timestamped
phase observations, not vendor billing/request records. Aggregate counters remain.
Acceptance rate uses confirmed accepted/rejected outcomes, otherwise null.
Historical counters have no invented timestamps. anonymized=true returns501;
global customer statistics, tier/SKU and latency buckets are not inferred.

## Other request paths
Generic UI video count1 supports supplied tokens, configured provider order and
explicit1–10 WAF-only attempt budgets through HTTP. SDK wrapper/CLI/queued MCP
provider mirrors are documented in [generic video controls](GENERIC_VIDEO_CAPTCHA.md).
Generic count2–4 uses one native request with all-output checkpointing and the
same provider/supplied-token controls. Supplied confidential queued MCP tokens
still refuse; direct SDK/CLI and private REST worker paths retain single-use scopes.

Native image2K/4K upscale supports supplied/provider tokens and explicit HTTP
captchaRetry1–10. Each positively confirmed refusal retry opens a fresh client,
proves owned image/project, and binds the selected enum (2K=1,4K=2). Supplied
tokens force one attempt. For4K, the current enabled detail-menu option is proved
before paid mint and checked again before dispatch; Disabled or missing
options refuse without a solver task. Accepted/unknown/mixed outcomes and late
download/save failures never replay. No entitled4K or solver-backed accepted
output is claimed from source tests.

Existing SDK native_captcha_token/native_captcha_provider scopes, CLI image
upscale --captcha-token-file and direct MCP captcha_token share the same one-use
2K/4K transport. Explicit retry budgets are private-worker/HTTP controls, not new
SDK/CLI/MCP upscale flags. Exports/GIF/local concatenation need no generation token.



Local event statistics now include durationMs only when the same observer instance
measured a matched solveStarted→solved/solveFailed or submitted→terminal phase
using a monotonic clock. Filtered summary.latency reports averageMs and sampleCount
for solver, confirmed Google acknowledgment and unknown terminal events separately.
Historical rows and unmatched/cross-worker phases have no invented duration.
Solver latency includes failed solves; acknowledgment latency excludes unknowns.
This measures local waits, not provider billing or Google's account reset time.
