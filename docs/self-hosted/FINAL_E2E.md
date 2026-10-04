# Final E2E campaign preparation

R12 is a separate acceptance campaign after feature implementation. A source test,
solver result, endpoint name or authentication check is not accepted Google output.
Run individual opted-in scenarios, not the whole paid marker tier.

## Entry checks
- Record deployed source revision, API/MCP health and empty per-profile queues.
- Read fresh models, tier, reference capacities and credits on each selected profile.
- Use the private campaign ledger and atomically reserve each permitted attempt
  before dispatch; do not print account credentials, protected URLs or prompts.
- Select the cheapest fresh compatible video model. Earlier refused attempts
  still count against the authorized limit; never replay an uncertain request.
- Start with read-only fixtures/attachment captures, then one representative output.
  Keep original assets and remove only invocation-owned temporary fixtures.

## Matrix
|Area|Representative acceptance|Additional free/read-only proof|
|---|---|---|
|Images|Text/local/native references; canonical mixed slots; Auto; decoded output|Fresh Lite10 and character/image weights; exact ordered ten-reference abort capture|
|Upscale|Native2K through CLI/REST/registered MCP; decoded dimensions|Higher-target entitlement refusal; override ownership before solving|
|Videos|Cheapest compatible generic and canonical native reference output|Fresh reference/edit/extension/promotion models and typed input budgets|
|Video operations|Native edit/extension/promotion, export/GIF; decoded output|Reuse owned sources; exact identity/dimensions and output checkpoints|
|Voices|Short real preview, saved metadata CRUD, owned playback, character binding|System presets, typed saved-user catalog/detail and explicit WAF/unknown outcomes|
|Inventory|Shared CLI/MCP/REST resume checkpoint with URL-free observations|Multi-page projects/catalog/history; exhaustion distinct from unknown completeness|
|Deletion|Own synthetic mixed/repeated registered aliases and receipts|Unknown raw IDs refuse; preserve original media|
|Accounts|Successful staged identity/project import and accepted-refresh continuity|Three independent health/queue reads; rejected candidate preserves originals|
|Jobs/API|Sync/async polling, exact output count, callbacks, safe recoverable unknown|Defaults, score selection, WebP conversion, inputsCount and local event filters|

## Surface coverage
CLI and direct registered MCP share SDK operations. Queued MCP and REST can
execute different workers, so verify those paths explicitly. Native direct MCP
adapters have no queued twin; do not imply one. Registered source now has42tools,
including gflow_sync_native_inventory. API route scopes are in [API.md](API.md).

## Current boundaries
Real browser and CapSolver audio previews were explicitly WAF-refused, with no
accepted saved voice. Refused attempts showed unchanged credits; that does not
prove successful audio is free. Successful cookie import is also unverified.
Three Pro accounts do not grant Ultra4K access. Generic numeric video seeds and
five distinct ratios lack a supported current generation contract.

Keep accepted output, explicit refusal, unknown outcome and pre-submit failure
separate. Stop on accepted/unknown partial writes, inspect retained actual handles,
and continue a different unblocked case. Extra paid allowance or human login is
requested only after the current authorized work and preparation are complete.
See [roadmap](PARITY.md#roadmap) and [verification](VERIFICATION.md).


Before final R12: the ten-reference picker failure is fixed and its live abort-only proof passed; run bounded observed account-resource continuation over character/voice kinds; verify generic count1–4 provider controls and2K refusal retry with remaining operator budget. Entitled4K requires an actually enabled account option; unavailable Pro tiers are refusal tests. Successful cookie import/renewal and accepted saved voice/audio binding remain prerequisites for their complete lifecycle tests. Whole-source tests and actual read proofs do not replace these acceptance checks.

Latest zero-credit proof: real pro1 count4 generic request carries four distinct IDs and was aborted before forwarding. Current retained budget: pro1 images2/videos2; pro2 images0/videos1; pro3 images1/videos1, plus one pro1 and two pro3 audio-preview refusals. Pro2 now reaches Google sign-in on fresh entry and needs human renewal. Pro1 had positive editor/principal proofs earlier, but its latest07:54-07:56 fresh identity checks failed; renew/recheck before its acceptance campaign. A count2–4 accepted batch needs additional per-account video allowance; no remaining account has two unconsumed video attempts.


## Executable scenario list

Run serially on one freshly authenticated profile. Each row is an individual
opt-in test file; do not enable an entire paid marker tier. These six files collect
ten scenarios successfully on the deployed source. Collection proves availability
of the harness, not successful Google execution.

| Test file under `tests/e2e/` | Explicit setup beyond common profile/home | Purpose |
|---|---|---|
| `test_native_inventory_sync_bdd.py` | `GFLOW_CLI_E2E_NATIVE_SYNC=1` | Two bounded checkpoint steps, private observations, zero generation |
| `test_native_asset_lookup_bdd.py` | `GFLOW_CLI_E2E_ASSET_LOOKUP=1`, `GFLOW_CLI_E2E_RESOURCES_PROJECT` | Fresh owned image/video metadata and content, no write |
| `test_native_image_ten_retention_bdd.py` | `GFLOW_CLI_E2E_TEN_RETAIN=1`, project, `GFLOW_CLI_E2E_TEN_MODEL` | Abort before generation; ten exact ordered identities; requires10fresh active owned images or explicit GFLOW_CLI_E2E_TEN_UPLOAD_FIXTURE=1 for owned upload/archive fixtures |
| test_native_image_ten_rendering_bdd.py | GFLOW_CLI_E2E_TEN_RENDER=1, TEN_OUTPUT private directory, project/model, owned fixture upload or explicit fixture, one reserved image | Separate paid acceptance; persistent invocation.marker forbids replay, validates exact ten-reference wire once and decoded owned output |
| `test_native_video_batch_preflight_bdd.py` | `GFLOW_E2E_BATCH_PROFILE_DIR`, `GFLOW_E2E_BATCH_PROJECT_ID` | One intercepted four-output Lite request, zero forwarding |
| `test_native_saved_voice_preview_bdd.py` | `GFLOW_CLI_E2E_SAVED_VOICE_PREVIEW=1`, private `GFLOW_CLI_E2E_SAVED_VOICE_FIXTURE` already reserved | One real preview, saved playback and owned cleanup; requires fresh accepted audio |
| `test_native_video_paths_final_bdd.py` | Exactly one `GFLOW_CLI_E2E_NATIVE_VIDEO_PATH`, private output/source configuration, `GFLOW_CLI_E2E_RUN_VIDEO=1`, `GFLOW_CLI_E2E_NATIVE_VIDEO_BUDGET=1` | One selected reference/edit/extension output; audio-reference also needs its separate one-preview reservation |

Common browser configuration:

```bash
export GFLOW_CLI_BROWSER_ENGINE=patchright
export GFLOW_CLI_HEADLESS=false
export GFLOW_CLI_E2E_HOME="$GFLOW_CLI_HOME"
export GFLOW_CLI_E2E_PROFILE=pro3
```

Load protected operator environment files before these exports; the selected
profile/project and any bearer headers remain private. Install the optional
engine using `uv sync --frozen --extra patchright`. An example read-only invocation,
after its explicit setup and fresh authentication checks:

```bash
uv run --frozen --extra patchright pytest -q -m 'e2e and e2e_auth'   tests/e2e/test_native_inventory_sync_bdd.py
```

Use the single scenario/node selector when a file includes multiple modes.
Reserve in the campaign ledger before any image/video/audio dispatch. An opt-in
flag or fixture is not itself a global-budget reservation. Refused or uncertain
submitted attempts keep their reservation; release only proven zero-forwarded
preflight failures. Never rerun an accepted/unknown scenario to make the test green.
Owned cleanup follows fresh identity checks and must preserve original assets.

## Latest entry readiness

Source `1e68b30c11736ac835b2d53217e8573b135c5575` is deployed on CC LXC.
The whole gate passed7,684tests/5skips/90%coverage. REST accounts/jobs/stats,
configured GUI and registered42-tool MCP reads passed. Deployed OpenAPI advertises
all18JSON/multipart methods; empty local-only deletion and duplicate-form refusal
passed with queues0 and zero Google generation.

The short pro3 resource calls returned valid opaque continuations but read zero
catalog pages. Longer calls still failed; its direct Google GetPeople returned401
after engine alignment. Do not treat the short responses as fresh authentication
or inventory proof. Pro2 previously reached Google sign-in; pro1's final post-alignment
GetPeople also returned401 after earlier successes. Renew/recheck all three profiles
before paid or saved-voice acceptance. Successful cookie import and automatic
renewal remain unverified. The service engine and optional dependency are now
explicitly aligned; this does not restore expired Google credentials.

Retained image/video attempts: pro1 2/2, pro2 0/1, pro3 1/1. In each pair the
first number is images used of50 and the second videos used of2. There are only
two remaining single-video attempts total, one on pro2 and one on pro3. A real
two-output batch on one account needs additional authorization. No new video was
submitted during the overnight window. Audio previews: one pro1 and two pro3,
all explicitly refused; successful audio cost remains unproved.


Local API readiness additionally has an actual deployed proof: one two-clip
FFmpeg job, async201/Location, same-key sync200 with the same jobId, completed
polling, inputsCount2 and decoded64x64/3second MP4. Invocation-owned local fixtures
were cleaned; Google generation0 and allowances unchanged. This local path can
run while Google access needs renewal; it does not validate native generation.


Current account isolation checkpoint — 4 October: pro1 is disabled and reserved for UseAPI, pro2/pro3 are the two testing profiles with fresh post-login access. No cookie-copy/import tests are permitted. The authoritative private campaign ledger counts pro2 images4/videos1/audio2 and pro3 images3/videos1/audio2 (pro1 images2/videos2/audio1 retained). Each active account has one video attempt remaining; image attempts may continue within50/account. Corrected ten-reference single-image BDD and fresh three-upload deletion-repeat/mixed BDD passed. Later reservations update the private ledger before submission; never reset these counters. Automatic renewal remains unverified.


## 4 October deployed acceptance follow-up

Deployed source 4a9e9d64c8235d1a909b6725828df70a4a8d26c9 passed the
mandatory source gate: 7,813 passed, 5 skipped, 89.64% coverage. REST, GUI
and registered 43-tool MCP entry checks passed.

* R01: one real registered MCP image request using an older owned library
  reference plus an invocation-owned character completed with one downloaded
  image. The fixture cleanup passed; there was no generation replay.
* R06: one REST image request explicitly selecting CapSolver completed with one
  accepted image. Local provider observations recorded solveStarted, solved,
  submitted and accepted. No captchaRetry was requested and no retry occurred.
  Previous solved-token requests were refused or uncertain; one acceptance does
  not prove automatic recovery from Google's unusual-activity errors.
* R07: deployed REST and registered MCP read-only capability calls on an owned
  generated image observed 2K available and 4K disabled. No upscale, solver or
  generation was dispatched by these reads.
* R10: the operator enabled the optional 1,800-second idle access interval.
  The first scheduled project-access checks completed OK for pro2 and pro3.
  Both returned profilePreserved=true and refreshAttempted=false. Disabled
  pro1 had no scheduled job. A second interval, long idle time and an actual
  authentication-renewal boundary remain unproved; this is not automatic renewal.

The retained private campaign counts are pro2 images5/videos1/audio2 and
pro3 images4/videos1/audio2; reserved pro1 remains images2/videos2/audio1.
Each active account still has one authorized video attempt remaining.
The two testing profiles are isolated from UseAPI; pro1 remains disabled
in gflow and reserved for UseAPI. No cookie-copy/import test was performed.

### What an unusual-activity error means here

The observed error stops the submitted generation. It is not an interactive
CAPTCHA prompt. A browser or CapSolver token may already have been submitted
before Google refuses the request. Token issuance and Google acceptance are
recorded separately. The response alone does not identify whether the token,
session, IP address or another request property caused the refusal.

Default behavior is one attempt. Explicit provider retries are bounded and
advance only after a positively established WAF refusal with no accepted or
unknown result. An uncertain outcome, accepted output, cancellation or supplied
single-use token is never automatically replayed.
