# CAPTCHA providers and supplied tokens

The normal image path uses Google's browser-owned token. Provider configuration is
optional. Adding a key does not silently change the default generation path.

## Configuration

Authenticated `POST /v1/google-flow/accounts/captcha-providers` accepts only
`CapSolver` and `2Captcha` string keys. An empty string removes that key. GET on
the same path returns `***configured***`, never the key. The implementation
atomically updates only `GFLOW_CAPSOLVER_KEY` and `GFLOW_2CAPTCHA_KEY` in the
service user's `~/.config/homelab/secrets.env`, retaining other lines and mode600.
Only ordinary alphanumeric, underscore and hyphen API keys are accepted.

Use an SSH tunnel or TLS when sending secrets across an untrusted network. Avoid
putting keys directly into shell command arguments or source files.

## Image requests

`POST /images` accepts `captchaToken`: 20–20000 characters, single submission.
It is mutually exclusive with `captchaOrder` and `captchaRetry`.

Provider generation is currently **guarded off**. `captchaOrder` and `captchaRetry`
return501 before queueing after normal validation, even when valid keys are configured.
Missing provider keys or malformed controls return422. The native browser
probe did not expose the actual reCAPTCHA action, so guessing an action or charging
a solver task would not establish a valid Google request. Retry values2–10 also
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
not enabled by the public generation endpoint until action capture is measured.

Clients use Enterprise v3 tasks according to
[CapSolver's documentation](https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/)
and [2Captcha's documentation](https://2captcha.com/api-docs/recaptcha-v3).
A solve has a bounded deadline and creates one task. The whole provider
sequence has a110-second deadline before Google submission. A timed-out
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
request. Live Google acceptance of third-party tokens still needs an operator
key and a successful test; this is not yet claimed as live verified.

The `accepted` statistic is conservative: it is recorded after Google returns an image and its download succeeds. A download failure can therefore undercount Google acceptance; it never counts a solved token alone as accepted.
