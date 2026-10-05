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
wire slots and one-shot rewrite have offline coverage. Manually supplied-token
acceptance remains unverified; provider-selected CapSolver image acceptance is
confirmed separately below. Ordinary browser-owned
image generation and native seed enforcement are independently live verified.

The provider clients below are enabled by explicit request controls. Their implementation and measured refusal paths do not prove Google acceptance.

Clients use Enterprise v3 tasks according to
[CapSolver's documentation](https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/)
and [2Captcha's documentation](https://2captcha.com/api-docs/recaptcha-v3).
A solve creates one task with a default deadline of120seconds. Fallback across
configured providers can take longer than one task's deadline. A timed-out
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
request. Earlier JavaScript hooks did not capture metadata; the native reload parser supersedes that failure. CapSolver image acceptance is confirmed through REST and queued MCP in [the final trials](FINAL_E2E.md#4-october-final-registered-imagevideo-trials). 2Captcha acceptance is unverified; compatibility is retained. Supplied-token slot rewriting remains guarded.

Acceptance is recorded from the exact matching native acknowledgement before later download/storage. A solved token alone never counts as accepted.

For a local masked key editor and credit-free balance check, see [the CapSolver GUI guide](CAPSOLVER_GUI.md). Saving a key does not automatically change generation or prove Google token acceptance.

A fresh same-page TokenMinter replacement was submitted in a live BDD but Google rejected it with unusual-activity/WAF 403. No accepted image was returned. This does not prove all external tokens fail, nor does it permit claiming a successful replacement path. Later CapSolver REST and queued MCP image requests were accepted; this earlier refusal remains evidence for its particular request.

Earlier refused CapSolver image trial: one paid task solved, one replacement request submitted to Google, zero accepted images (`solveStarted=1`, `solved=1`, `submitted=1`, `accepted=0`). Google rejected unusual activity (gRPC 7/HTTP 403); no retry was made. Explicit provider controls are now available; the GUI capability indicator follows whether a key is configured, and does not claim Google acceptance. A provider solution is distinct from Google acceptance.

Statistics record `rejected` for an exact terminal Google refusal during generation. Only a typed unusual-activity WAF rejection with matching negative dispatch evidence can permit an explicitly bounded retry; quota/access refusals do not. Post-submission timeouts or mixed/unknown acknowledgements record unknown. An exact accepted acknowledgement stays accepted after a later download failure. These counters never trigger automatic solving or generation retries.

Native reference/edit/extension/promotion/TTS supplied-token and provider scopes are implemented;
see [exact native scope and verification](NATIVE_CAPTCHA.md). Native provider-backed
Google acceptance remains unverified; REST and queued MCP image acceptance is confirmed.


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
2K/4K transport. SDK service, CLI and direct MCP image-upscale provider order/retry mirrors
are also implemented; see [native controls](NATIVE_CAPTCHA.md#reference-edit-extension-and-image-upscale-clidirect-mcp-provider-controls). Exports/GIF/local concatenation need no generation token.



Local event statistics now include durationMs only when the same observer instance
measured a matched solveStarted→solved/solveFailed or submitted→terminal phase
using a monotonic clock. Filtered summary.latency reports averageMs and sampleCount
for solver, confirmed Google acknowledgment and unknown terminal events separately.
Historical rows and unmatched/cross-worker phases have no invented duration.
Solver latency includes failed solves; acknowledgment latency excludes unknowns.
This measures local waits, not provider billing or Google's account reset time.

## Generic image CLI and queued MCP mirrors

Single-prompt `image t2i`/`i2i` and registered queued `gflow_generate_image`
mirror configured image provider order and 1–10 total attempts through the existing
ImageOverrides engine. None omission bypasses the wrapper and preserves browser
behavior. Existing project/native UI prechecks and exact image refusal evidence
are required; downloads and metadata writes stay outside retries. Queued token or
secret-pointer inputs refuse. Offline tests cover the safeguards; queued MCP text-image CapSolver acceptance
is recorded in the final trials below. CLI and other adapter acceptance is separate.
See [generic image controls](GENERIC_IMAGE_CAPTCHA.md) for exact public/queue scope.

## R06 coverage and evidence

R06 closes implementation and safeguards. All optional provider controls reuse
existing image/video/native policies. Ordinary omission keeps the browser token
path; CapSolver requires explicit selection. Provider order is configured, unique
and nonsecret; retry means1–10 total attempts. Public SDK/CLI/MCP can combine order
and retry; REST deliberately accepts one of token/order/retry. Supplied token
conflicts fail before file consumption, solving or dispatch, including inherited
SDK/native scopes. Configured keys remain private and masked. Missing explicit-order keys refuse
at execution before metadata or solving, including removal after queue admission;
retry-only selection uses the existing configured provider order.

| Operation | Implemented interfaces and worker policy | Deliberate restrictions / missing implementation | Actual acceptance evidence |
|---|---|---|---|
| Image generation | Python image wrapper, single-prompt CLI t2i/i2i, queued MCP, REST image worker; ImageOverrides | Queued secrets refuse; supplied tokens use private REST worker only. Explicit project UUID and loaded native HTTPS/UI session required; unsupported hosts/transports and CLI multi-prompt/manifest controls refuse. No missing supported control. | One CapSolver REST image and one queued MCP text image accepted; native-reference provider and CLI trials WAF refused. |
| Generic video count1–4 | Python video wrapper, CLI t2v/i2v/r2v, queued MCP, REST general worker; VideoOverrides | Queued secrets refuse; SDK/CLI/private REST supplied tokens one use; explicit project UUID and native session required. No missing supported control. | Pre-dispatch body/reload capture; no accepted provider-rendered generic video. |
| Native reference video | Python native service/scopes, CLI reference-native, direct MCP, REST reference worker; native policy | Direct MCP only; fresh owned references/model capacities. No missing supported control. | WAF and quota/access refusals; zero accepted video. |
| Native edit / extension | Python native service/scopes, CLI edit-native/extend-native, direct MCP, REST edit/extension workers; native policy | Direct MCP only; fresh eligible owned source/model. No missing supported control. | Zero-generation construction; extension WAF refused. Accepted rendering pending. |
| Native image2K/4K upscale | Python native service/scopes, CLI image upscale, direct MCP, REST upscale worker; native policy | Fresh enabled4K option before solve/dispatch. No missing supported control. | Browser2K accepted/decoded; provider upscale acceptance and entitled4K pending. |
| Native video upscale / promotion | Python native service/scopes, CLI upscale-native, direct MCP, REST promotion worker; native policy | Explicit native operation; export/GIF/local work requires no token. No missing supported control. | Fresh model/source construction only; provider rendering pending. |
| Saved-voice preview / creation | Python saved_voice_operation(create)/scopes, CLI voice create, direct MCP, REST voice worker; native policy | Preview is the internal creation step, followed by saves; no separate public preview endpoint. No queued secret tool. No missing supported control. | Backend CapSolver/browser WAF or quota/access refused. Frontend voice acceptance is separate; backend creation remains pending. |

Native and generic supplied-token dispatch now records `submitted` and one
`accepted`, `rejected` or `unknown` outcome under local `supplied` / filtered
`UserProvided`; no solving event is invented. The existing `CaptchaStats` database
is resolved from `GFLOW_SELFHOST_ROOT` (otherwise the configured gflow home's
selfhost directory). SDK/CLI invocations must load the operator environment to
share the service root. Tokens/keys never enter statistics, durable DTOs or public
results. Consumed-but-unsubmitted tokens emit no submission; cancelled/interrupted
submitted scopes emit unknown once; late inherited callbacks cannot alter it.
Acceptance survives later download/save/teardown failure. Historical missing
supplied-token observations are not reconstructed.

Existing final trials and exact acceptance evidence are in
[FINAL_E2E.md](FINAL_E2E.md#4-october-final-registered-imagevideo-trials) and
[VERIFICATION.md](VERIFICATION.md#4-october-deployed-acceptance-follow-up).
No demonstrated current context/action/forwarding defect explains the refused
voice/video calls. Their precise remaining question is whether a correctly scoped
request on a fresh original authorized profile can obtain an exact positive
acknowledgement and usable output. The refusal does not identify its cause and
CapSolver does not guarantee acceptance. See the
[bounded operation-specific R12 plan](FINAL_E2E.md#r06-operation-specific-r12-campaign).
