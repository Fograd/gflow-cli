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

Provider generation is currently **guarded off**. `captchaOrder` and `captchaRetry`
return HTTP 501 before queueing after normal validation, even when valid keys are configured.
Missing provider keys or malformed controls return 422. Native reload probes now measure the actual action/site key, but a fresh same-page replacement was rejected for unusual activity. Actual CapSolver/2Captcha acceptance remains unproven. Retry values 2–10 also
lack Google-refusal retry semantics. Configuration and statistics routes remain
available for future integration.

Other generation, voice and export operations reject these controls explicitly.
A Google rejection does not trigger automatic generation. Tokens are single-use;
callers must not reuse them for another job.

The supplied-token hook replaces both observed token contexts in the validated
`ogiZ0b` request. It checks project, output count and envelope shape before
submission; an unfamiliar shape aborts. Tokens never enter durable job JSON:
a private temporary file is consumed and removed by the worker. The browser still
mints its own token, then the outgoing request uses the supplied override. The
wire slots and one-shot rewrite have offline coverage, but live acceptance of an
externally supplied replacement token remains unverified. Ordinary browser-owned
image generation and native seed enforcement are independently live verified.

The provider clients below are implemented and tested as preparation; they are
not enabled by the public generation endpoint until actual third-party replacement acceptance is proven.

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
this instance only. `accepted` is recorded only after Google returns generated
image records. `submitted` is an observed transport submission; neither a solved
token nor a configured key proves Google acceptance. The database contains no
keys, tokens or provider task bodies. Global useapi statistics and anonymised
cross-customer comparisons are not reproduced.

Provider task contracts, key preservation/masking and malformed-response paths
are tested offline. Native request token slots were observed with an aborted
request. Earlier JavaScript hooks did not capture metadata; the native reload parser supersedes that failure. Provider controls are implemented, but actual CapSolver/2Captcha replacement acceptance remains unverified. Supplied-token slot rewriting is guarded; current live evidence must be checked in VERIFICATION.md before claiming acceptance.

The `accepted` statistic is conservative: it is recorded after Google returns an image and its download succeeds. A download failure can therefore undercount Google acceptance; it never counts a solved token alone as accepted.

For a local masked key editor and credit-free balance check, see [the CapSolver GUI guide](CAPSOLVER_GUI.md). Saving a key does not automatically change generation or prove Google token acceptance.

A fresh same-page TokenMinter replacement was submitted in a live BDD but Google rejected it with unusual-activity/WAF 403. No accepted image was returned. This does not prove all external tokens fail, nor does it permit claiming a successful replacement path. Actual CapSolver acceptance still needs a successful controlled live Google test before removing the provider-generation guard.

Actual CapSolver proof: one paid task solved, one replacement request submitted to Google, zero accepted images (`solveStarted=1`, `solved=1`, `submitted=1`, `accepted=0`). Google rejected unusual activity (gRPC 7/HTTP 403); no retry was made. Public provider generation continues to return HTTP 501 and GUI generationEnabled remains false. A provider solution is distinct from Google acceptance.

Statistics record `rejected` only for a typed Google WAF refusal during generation. Post-submission timeouts, unknown errors and download failures record `unknown`; they are not labelled rejection. `accepted` is counted after a successful download, so it is a conservative completed-image observation. These counters never trigger automatic solving or generation retries.

Native reference/edit/extension/TTS supplied-token scopes are now implemented;
see [exact native scope and verification](NATIVE_CAPTCHA.md). Provider-backed
Google acceptance remains unverified and generation remains guarded.
