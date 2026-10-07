# Final E2E campaign preparation

R12 is a separate acceptance campaign after feature implementation. A source test,
solver result, endpoint name or authentication check is not accepted Google output.
Run individual opted-in scenarios, not the whole paid marker tier.

## R12 measured campaign — 5 October 2026

The additional campaign started from `9456ebc00b2d8c829867703c1901b620f0a5102f`.
Only the original pro2/pro3 profiles were used. Pro1 stayed disabled and reserved
for UseAPI. The allowance was 20 image, 5 video and 2 audio-preview attempts per
account, plus 10 paid solver tasks across both accounts, without purchases or
top-ups. Historical counters were preserved separately. Atomic reservations
preceded dispatch; plural outputs and native upscales/promotions counted in their
applicable allowance. Every actual refusal retained its slot. Only demonstrated
zero-Google/zero-solver preflight failures released reservations. Requests made
one attempt; no hidden retry budget was enabled.

### Measured output and refusal matrix

|Case|Account / deployed interface|Result and proof|
|---|---|---|
|I1|pro2 REST async; Nano2; 16:9; count 1|Accepted JPEG, 1376×768; white clay rabbit, red scarf, yellow mug and teal table|
|I2|pro3 queued registered MCP; NanoPro; local I1 reference; 3:4|Accepted JPEG, 896×1200; reference identity preserved|
|I3|pro2 REST sync; NanoLite; native image + owned character; Auto; count 2|Two distinct JPEGs, 1376×768; first reference resolves 16:9; carrot added|
|I4|pro3 queued MCP; NanoLite; local first-reference Auto|Accepted JPEG, 896×1200; 3:4 approximation reported; blue star added|
|I8|pro2 REST async; NanoLite; distinct uploaded environment + owned character; Auto|Accepted JPEG, 1376×768; rabbit/ears/scarf from character and table/mug/background from separate reference visually present|
|I5r|pro2 REST async native 2K, exact I1 identity|Accepted 2752×1536 JPEG; both source dimensions doubled natively|
|I6|pro3 direct registered MCP native 2K, exact I2 identity|Accepted 1792×2400 JPEG; both source dimensions doubled natively|
|V1r|pro2 REST queued Lite T2V|Google accepted 8s, 1280×720 H.264/AAC; original job failed at local decoding; exact original MP4 recovered via MCP without regeneration|
|V2|pro3 queued MCP Fast start/end frames|Google accepted 8s, 1280×720 H.264/AAC; guard rejected measured Fast key; exact original recovered; carrot appears between start/end frames|
|B1|pro2 isolated SDK diagnostic Lite T2V|Reserved new attempt captured current video-record layout; accepted 8s original recovered without replay|
|B2|pro2 REST async Lite T2V after deployment|Completed job and one downloadable MP4, 8s, 1280×720 H.264/AAC; identity and requested scene visually checked|
|V2r|pro3 queued registered MCP Fast start/end after deployment|Completed task and one MP4, 8s, 1280×720 H.264/AAC; rabbit/mug preserved and carrot enters foreground|
|A2|pro3 direct MCP saved Puck preview; CapSolver 1|Explicit `no0P6` Google refusal: `PUBLIC_ERROR_UNUSUAL_ACTIVITY`; no accepted saved voice|
|V3|pro2 direct MCP native image + character references; cheapest 4s/360p family; CapSolver 1|Explicit `MZZa6b` Google refusal: `PUBLIC_ERROR_UNUSUAL_ACTIVITY`; no output|
|V6|pro3 direct MCP native 1080p promotion|Explicit `p0UkFb` Google refusal: `PUBLIC_ERROR_UNUSUAL_ACTIVITY`; no promoted output|
|V5r|pro2 direct MCP native Lite extension; CapSolver 1|Repaired owned-source measurement passed; `fZytfe` explicitly refused with gRPC 8, `PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC`|
|V4u|pro3 REST async Omni native edit; cheapest 360p model; CapSolver 1|Repaired source measurement passed; `jIps6` explicitly refused with gRPC 8, `PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC`; typed failed job retained|
|L1|SDK free export of existing owned clip; billable RPCs blocked|Original MP4 1280×720 and animated GIF 480×270 both decoded, 8s; actual browser downloads; zero billable forwarding|
|L2|REST local concatenation of two existing owned clips|Initial lookup/cache failures fixed; deployed Mac-localhost REST returned one decoded 14s, 1280×720 H.264/AAC clip, 30fps/48kHz, inputsCount 2. Same-job download representations have identical SHA-256.|
|L3|pro3 registered MCP free export of V2|Accepted animated GIF, 480×270, 8s, exact source identity; no new video generation|
|CB1|Isolated runtime callback worker and controlled loopback receiver|One HTTP 204 delivery; exact stored job snapshot received; production configuration unchanged. Public delivery was not tested.|

Eight image outputs and five generated clips were preserved locally under the
Mac project's `R12_OUTPUTS/`, with derived export/GIF files, measurements and an
HTML review gallery. Root `R12_HANDOFF.md` provides clickable local files, exact
identities, final revision, services and follow-up instructions. Protected raw
responses, signed URLs, journals and the atomic ledger remain outside Git.

### Original 5 October allowance, credits and skipped capabilities

|Account|Images used / remaining|Videos used / remaining|Audio used / remaining|Fresh Google credits before → after|
|---|---|---|---|---|
|pro2|6 / 14|5 / 0|0 / 2|1050 → 1020|
|pro3|3 / 17|4 / 1|1 / 1|1050 → 1010|

Solver observations reconcile exactly: 4 started, 4 solved, 4 submitted and
4 explicitly rejected; 0 accepted, failed or unknown new tasks. Six tasks remain.
A solved token did not establish Google acceptance. The original REST 2K failure
I5 conservatively retains one image slot because zero forwarding was not proved.
Unsupported low-priority T2V, invalid harness URLs/controls and guarded frame
probes have explicit zero-forwarding evidence; their released entries remain.

Fresh video discovery advertised no 4K model on either account. Fresh pro3 image
capability inspection showed disabled 4K. Initial pro2 capability-menu timeouts
remain unknown observations, so they are not presented as disabled entitlement.
No 4K generation was attempted. Historical ten-reference acceptance was reused.
A second audio-preview refusal on an unchanged path was not purchased. Saved
voice playback/CRUD/binding and audio-reference video remain blocked because no
voice was created. Successful audio being free is unproved. Authentication was
observed working; automatic renewal across expiry was not observed.

### Focused fixes, recovery and validation

The fixes retain original profiles, account/project/workflow ownership checks,
leases and startup defaults. No dependencies changed and no upstream PR was
merged. At the original R12 close, PR907 was inspected but not ported. The separately authorized follow-up below preserves that historical result.

1. Accept exactly the measured Fast first/last model key while requiring both
   invocation-bound frame UUIDs.
2. Decode a single positively identified current media/project/workflow video
   record alongside legacy CAE records; reject ambiguous or malformed records.
3. Measure a fresh owned MP4 when edit/extension metadata omits both dimensions;
   partial or unsupported aspect evidence still refuses.
4. Capture bounded browser downloads alongside page blobs for video/GIF export;
   validate output magic and clean up listeners/tasks on timeout/cancellation.
5. Measure bounded, freshly owned native-cache MP4 bytes when both metadata
   dimensions are absent; keep partial/invalid/mismatched metadata, scope and
   private-path checks strict.

The original failed V1r/V2 jobs were not rewritten as successes. Their exact
accepted output identities were downloaded and validated without another Google
submission. B2/V2r are separate reserved retests of the deployed fixes.

Live tagged BDD checks passed for current owned metadata/MP4 measurement,
actual bound Fast frame requests fulfilled locally before forwarding, original
MP4/GIF export with billable RPCs blocked, and fresh owned native-cache bytes.
Harness failures were recorded and corrected without generation replay.
Required hygiene, links, privacy, generated mirrors, council references, lint,
format and strict types passed. Final quiet suite: 8,293 passed, 5 skipped,
90.14% coverage. The preceding run had one unchanged virtualized-picker DOM
failure and 8,292 passes; that test passed isolated, then the quiet whole run
passed. The earlier run is not claimed all-green. Runtime revisions were
`957395f9d9a3595db7f4bd89f6543eb63564cf5c` then
`b8d701cb295ea0e027cbb5e89dba90a21f8ff589`, published atomically to all three
requested branches and deployed after idle-queue checks, SQLite/config backup
and quick checks. API/MCP/solver-GUI services were active and protected
configuration unchanged. Final documentation revision has the same tested
runtime; root R12_HANDOFF.md records its exact SHA and localhost verification.

Invocation-owned uploads and the character were cleaned up after positive image
results. All other observed active media remained present. Pro3's initial
post-archive read was stale; a fresh browser context confirmed the acknowledged
archive without replay. No original or historical fixture was removed.

R12 is a representative executed campaign with external refusals, not full paid
acceptance. Native reference rendering, audio, edit, extension, promotion and
public callback delivery remain unchecked until their real requirements pass.

## Authorized PR907 follow-up — 6 October 2026

After the initial R12 close, the user authorized a narrow repaired port of PR907's alternative startup. `GFLOW_CLI_CDP_LAUNCH` remains false by default; normal launch flags, request contracts, selectors, retries and dependencies are unchanged. Native Flow only, headed Patchright, installed system Chrome, an original managed profile and Linux user systemd are required. No arbitrary-browser attachment, cookie import or profile replacement is allowed. [Configuration](../CONFIGURATION.md#gflow_cli_cdp_launch) and [plan](../superpowers/plans/2026-10-05-owned-cdp-launch/PLAN.md) describe scope ownership and rollback.

The free BDD passed four ordinary/CDP comparisons through shared-client and standalone-image launch paths, with actual original pro3 identity/owned V2 video, 1010 credits, requested language/header/viewport, webdriver false, loopback debugger, graceful Chrome exit and lease recovery. No generation or solver task occurred. Startup findings were fixed: migrated accounts do not require the obsolete labs cookie; standalone CDP needs its locale language header; LXC process cleanup needs both the invocation scope and Chrome's exact fresh-PID desktop scope. An incompatible crash-reporter-disable experiment was removed. Original failed-test evidence and the positively identified process recovery remain private.

The final pro3 video slot was atomically reserved as V6c, then submitted once through the registered MCP tool on the deployed repaired launch path. Fresh Mac-forwarded discovery advertised `veo_3_1_upsampler_1080p`; original account balances before the test were 1020/1010. Existing V2 was the exact owned source; no new reference upload was needed.

|Case|Account / interface / model / controls|Reservation and evidence|Classification|
|---|---|---|---|
|V6c|pro3 registered MCP `gflow_upscale_native_video`; Veo 3.1 1080p upsampler; retained 8s 720p V2; count1|One video slot, zero solver tasks; exact source/project; one `p0UkFb` submission; durable private checkpoint and typed response|Google explicitly refused: `PUBLIC_ERROR_UNUSUAL_ACTIVITY`, gRPC7 / WAF403; zero outputs|

The first harness run used the nonexistent `Tool.inputSchema` field and failed before its dispatch checkpoint or mutating call; the installed SDK uses `Tool.input_schema`. This demonstrated zero Google/solver submissions; the same reservation was retained while that one-line test-field error was corrected. The subsequent run made exactly one mutating call and received the explicit refusal. The paid BDD therefore failed acceptance as expected from the recorded response; it is not called green. The deployed journal proves owned CDP startup and graceful reap around that exact submission. There was no automatic retry, provider fallback, paid solver or unknown promoted output to replay.

This does not demonstrate improved acceptance or establish startup as the refusal's cause. The older default-path refusal and this test occurred at different times. The repaired option stays false by default; the invocation-owned MCP runtime drop-in was removed after idle checks. All three services are active and protected environment files were preserved. No public browser-control service was exposed.

|Final R12 allowance|Images used / remaining|Videos used / remaining|Audio previews used / remaining|
|---|---|---|---|
|pro2|6 / 14|5 / 0|0 / 2|
|pro3|3 / 17|5 / 0|1 / 1|

CapSolver remains 4 used / 6 remaining. Fresh post-test balances remain pro2 1020 and pro3 1010; this rejected promotion had zero observed credit decrease. Both video allowances are exhausted; further video attempts require new approval. Image counts 6/20 and 3/20 describe consumed allowance, not success rates. The original eight accepted images/five generated clips and all historical counters remain intact. Native promotion, reference/edit/extension/audio acceptance, automatic authentication renewal and public callback delivery remain unproved.

Runtime publication: `157086bab74ba2bf5c1376a0869c735224fa1616`, aligned on all three authorized branches and deployed after idle queue/worker checks and private SQLite/config backups. The tested runtime tree passed 98 focused checks, strict static/doc/privacy/type gates and a quiet full suite: 8371 passed, 5 skipped, 89.99% coverage; the required 80% threshold was also independently rechecked. Earlier full runs retained one unchanged DOM failure and one scaled-budget timing failure; both passed focused (9 tests). A runner quoting error briefly changed the quiet command's threshold to40; measured coverage was89.99 and the separate required80 check passed. The corrected runner enforces80. No dependency or timer change was made.

The final documentation/test-harness revision, final required gate and Mac localhost verification are recorded in root `R12_HANDOFF.md`. Implementation checkboxes remain complete; no paid acceptance item is checked by these refusals. Private evidence: `r12-pr907/V6c-checkpoint.json`, `V6c-pre-dispatch-proof.json`, `runtime-manifest.json`, and protected journals. Public-safe Mac startup and balance evidence are in `artifacts/r12-pr907-*.json`.

## PR882 focused comparison and recovery repair — 7 October 2026

[Upstream PR882](https://github.com/ffroliva/gflow-cli/pull/882) remains open at
`30365f520458f48eaa3257c09d32a12864e84106`. Its scene-based `video extend`
uses operation enum2, source workflow, a scene source-path and a last-second
24fps frame window. R12 V5r used standalone `extend-native` / REST
`videos/extend` / registered `gflow_extend_native_video`: enum1, source media,
preassigned independent output identities and no scene. The shared RPC name
`fZytfe` does not make these request schemas interchangeable. No scene payload,
whole PR, dependency change or speculative refusal fix was ported. Current
upstream checks include failed Python3.13 tests and cancelled3.11/3.12 runs;
the captured failure has six outdated CLI mocks without `create_scene_for_extend`.
The author's reported scene output is separate upstream evidence, not CC proof.

Comparison exposed a demonstrated local download gap: both extension worker and
MCP could report arbitrary HTML bytes as an MP4 without a fresh workflow check.
Six regressions failed before the repair. Both now share checkpoint-bound
recovery: exact ordered output count/media/project/workflow, fresh owned video
metadata and the existing bounded unauthenticated native downloader. Protected
URLs refresh before download. Redirects, wrong identities/types/dimensions,
non-MP4 content and destination replacement refuse. Partial validated siblings
remain on disk; cancellation cleans temporary files and propagates; failures
retain original handles as nonretryable uncertainty without generation replay.
Public parameters, request DTO, model choice, retries and browser defaults did
not change. CLI and REST use the shared worker; direct MCP uses the same helper.
Native editing/reference download paths were outside this focused repair.

|Free case|Actual result|Cost and limits|
|---|---|---|
|Local worker/MCP invalid content, wrong workflow and foreign URL|Red before repair; green after|Controlled requests only; no Google dispatch|
|Plural MP4, partial failure, mid-stream cancellation and existing destination|Validated sibling preserved, temporary bytes removed, exclusive write enforced|Local generated fixture only|
|Original pro3 retained V2 through extension poll/download helpers|Exact identities; decoded1280×720 MP4,1238267bytes, SHA256 `ad2a07eac2393b728875d4f7f13c9b1d7ca9391178def6c45b2cccea6c3bb775`, identical to original|Zero generation/solver; balance1050 before/after|
|Mac localhost REST and registered MCP before deployment|Original B2/L2f jobs and download hashes preserved; V4u refusal retained;43tools; pro1 disabled; balances1050/1050|Read-only; solver observations unchanged|

One tagged free browser BDD passed with mutations denied before bootstrap,
original stored account verified, cookie import/token mint disabled and normal
startup. Unknown background RPCs were aborted, not forwarded. Two earlier runs
retrieved/decoded the clip but failed overstrict harness assertions (background
RPC blocking and an assumed `UpteDb` request); both retained their owned output
directories and submitted zero generations. The final evidence explicitly uses
an existing generic clip, not a newly accepted extension. Independent static
correctness/security/compatibility reviewers found no blocker; their stream
cancellation test suggestion was added and passed. Required final gates and
publication/deployment evidence are recorded in root `R12_HANDOFF.md`.

Fresh balances are pro2/pro3 **1050/1050**, superseding older1020/1010 readings.
This balance refresh does not reset allowances: pro2 images6/20, videos5/5,
audio0/2; pro3 images3/20, videos5/5, audio1/2; solver4/10. Ledgers and historical
usage remain unchanged. No paid acceptance checkbox changes. Standalone
extension remains Google-refused; testing improved acceptance requires a new
explicit video allowance. Automatic renewal and public callback delivery remain
separate unproved items.

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
adapters have no queued twin; do not imply one. Registered source now has43tools,
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


Historical preparation snapshot, superseded by the [R06 R12 campaign](#r06-operation-specific-r12-campaign): the ten-reference picker failure is fixed and its live abort-only proof passed; run bounded observed account-resource continuation over character/voice kinds; verify generic count1–4 provider controls and2K refusal retry with remaining operator budget. Entitled4K requires an actually enabled account option; unavailable Pro tiers are refusal tests. Successful cookie import/renewal and accepted saved voice/audio binding remain prerequisites for their complete lifecycle tests. Whole-source tests and actual read proofs do not replace these acceptance checks.

Historical zero-credit/budget snapshot (no current allowance): real pro1 count4 generic request carries four distinct IDs and was aborted before forwarding. Current retained budget: pro1 images2/videos2; pro2 images0/videos1; pro3 images1/videos1, plus one pro1 and two pro3 audio-preview refusals. Pro2 now reaches Google sign-in on fresh entry and needs human renewal. Pro1 had positive editor/principal proofs earlier, but its latest07:54-07:56 fresh identity checks failed; renew/recheck before its acceptance campaign. A count2–4 accepted batch needs additional per-account video allowance; no remaining account has two unconsumed video attempts.


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


### Registered MCP saved-voice and shared stats follow-up

Deployed source7eed4278c31a5b0d6c98e8501fedbc0076754386 exposed the new
saved-voice/promotion provider fields on the registered43-tool MCP service.
One explicit CapSolver saved-voice request on the isolated second account
recorded one solve, solved token, submission and rejection. Google returned a
typed quota/model-access refusal (429), not an unusual-activity error. No accepted
preview or acknowledged media handle was returned; the request was not replayed.
The cause within quota versus account/model access remains unobserved.
Accepted saved-voice playback/binding remains a separate proof requirement.

The deployed MCP process initially used the default private stats root while
REST used its configured root. The operator aligned GFLOW_SELFHOST_ROOT in
the shared protected environment, restarted MCP/GUI after empty queues, and
verified the running MCP environment. Both counter databases were backed up;
the four unique MCP observations were imported once with an atomic receipt.
No Google request, cookie/profile transfer or generation was performed by that
alignment. SDK/CLI/MCP processes must load the same configured root to contribute
to the same instance statistics; aggregate history remains locally observed,
not a Google account-wide usage total.

Retained campaign counts are nowpro2 images5/videos1/audio3 andpro3
images4/videos1/audio2. Reservedpro1 remains images2/videos2/audio1.
Each testing account retains one authorized video attempt. The private operator
audio bound is3 per account; this request's reservation was conservatively kept.

Second scheduled idle checks also completedOK: pro2 at16:52:39UTC and pro3 at16:53:13UTC, approximately30minutes after their first checks. Both preserved the original profiles and attempted no authentication refresh. The reserved disabled profile remained excluded. An actual renewal boundary and long unattended retention remain unproved.


### Remaining native public CAPTCHA mirrors gate

Native reference-video, edit, extension and image-upscale CLI/direct MCP
provider controls passed296 focused tests and both independent reviews.
The complete mandatory source gate passed7,875 tests,5 skipped, with89.85%
coverage. Hygiene, docs/mirrors, lint/format and types passed. No new live native
video or image-upscale provider acceptance is claimed by this gate.

One registered MCP saved-voice request onpro3 selected CapSolver explicitly,
recorded solveStarted/solved/submitted/rejected in the shared REST-visible
stats root, and ended with a typed WAF unusual-activity refusal. There was no
accepted audio, unknown result or retry. This differed frompro2's quota/access
refusal; neither establishes the cause of Google's decision. Retained counts:
pro2 images5/videos1/audio3;pro3 images4/videos1/audio3. Reservedpro1 remains
images2/videos2/audio1. Saved-voice playback/binding acceptance is still open.

A fresh queued project-access check after the pro3 unusual-activity refusal completedOK at17:02:25UTC, with profilePreserved=true and refreshAttempted=false. That refusal did not invalidate project access in this measured case; it does not prove all future refusals will preserve the session. The read made no generation or solver call.


### R06 generic image provider mirrors — 4 October

Single-prompt image CLI and registered queued MCP now expose optional provider
order and bounded attempt controls. The durable queue carries only nonsecret
camelCase fields; codec and daemon validate them. Selected calls reuse the
existing image policy, require an explicit owned project and observed native
HTTPS/UI transport, and retry generation only after a correlated WAF refusal.
Downloads, recording, accepted/unknown results and cancellation never replay.
Omitted controls preserve the original browser path. Multi-prompt/file/stdin
CLI batches refuse these controls explicitly. See
[GENERIC_IMAGE_CAPTCHA.md](GENERIC_IMAGE_CAPTCHA.md).

The incremental feature passed341 focused tests and both independent reviews.
Full integration verification and registered live image acceptance are recorded
separately; focused tests do not establish Google acceptance.


Full integration verification:7,919passed,5skipped,27warnings,
89.86%coverage in305.33seconds. Whole-tree types, lint/format, documentation,
website mirrors and existing council references passed. The duplication proxy
reported existing code outside this feature's changed blocks; it found no new
provider adapter duplicate. The deployed predecessor also passed six registered
native token/provider conflict boundaries with an unregistered fixture profile,
zero browser operations, solver tasks or generation. Live generic image
provider acceptance remains pending.


### 4 October final registered image/video trials

Tested/deployed implementation:5746bf617b18514b7bdce2a56961277d724a59ea.
The generic image provider fields are present on the registered MCP queue path.

* A count-one native-reference/Auto MCP image selected CapSolver, recorded one
  solve/submission/rejection and ended in a typed WAF refusal. No accepted output,
  unknown result or retry was reported.
* A separate text-only registered MCP image selected CapSolver and completed
  with one decoded1024x1024 image and shared solved/submitted/accepted events.
  This proves the queued provider path for that request, not universal recovery.
* A native-reference Auto MCP image using the default browser path completed
  with one decoded1024x1024 image, matching native project identity and verified
  derived-first-reference aspect metadata. This establishes native UUID Auto
  acceptance through registered MCP separately from the CapSolver refusal.
* The third profile's single-prompt CLI CapSolver image was refused for unusual
  activity, with exit10, one solve/submission/rejection and no automatic replay.
* One registered native reference-video request used an owned image plus the
  freshly observed Charon system preset. Its cheapest compatible model reported
 4credits/360p. CapSolver solved/submitted once; Google returned a typed
  quota/model-access refusal. No accepted video or unknown result was reported;
  the cause within quota versus access remains unobserved.
* The third profile had no existing active video in its selected project.
  One owned synthetic8-second640x360 MP4 was uploaded. Its acknowledged identity
  survived a subsequent read failure; a fresh cold read recovered that same
  source without reuploading and preserved every original media identity.
  One registered extension request selected the fresh cheapest compatible
 10-credit model and used the browser path once. Google returned a typed WAF
  refusal. The acknowledged fixture was then deleted; fresh inventory confirmed
  cleanup and preserved all originals.

No paid operation was replayed. The reference-video helper initially stopped
during read-only preset preflight because it expected an internal voice key
instead of the public name field. Its summary and ledger proved zero invocation
and zero reservation before correction; only the subsequent public generation
was counted. Operator proof artifacts remain private.

Cumulative conservative campaign counts are nowpro2 images8/videos2/audio3 and
pro3 images5/videos2/audio3. Reservedpro1 remains images2/videos2/audio1 and is
disabled in gflow. Both testing accounts have reached the authorized two-video
attempt limit; further video attempts require additional permission. Image
allowances remain, but these results do not justify repeatedly submitting an
unchanged refusal. The private audio bound remains three per test profile.

Video rendering/promotion/edit/extension and saved-user audio acceptance are
still unfinished. Accepted image and read-only proofs do not close those gaps.
No authentication renewal or cookie-copy/import test was performed.


Fourth scheduled project-access checks completedOK after the final refusals:
pro2 at17:53:13UTC andpro3 at17:53:42UTC. Both preserved original profiles,
attempted no authentication refresh and remained enabled; reservedpro1 stayed
excluded. Thus these measured refusal cases did not invalidate project access.

A separate registered credit-balance read returned guarded Unexpected Error500
for both profiles. It established no balance, quota exhaustion or logout.
That concrete public-read defect is being corrected independently; it does not
explain Google's generation refusals without additional evidence.


### R11 native credit browser-context correction

The registered credit-read500 was reproduced as Patchright evaluating native
page data in an isolated world. The reader omitted the shared
page_owned_evaluate_kwargs used by other native calls. The minimal correction
selects the page-owned context for Patchright and preserves Playwright behavior;
it changes no account authentication, cookie handling, solver or generation.

The real intercepted browser test reproduced the same cfb2h TypeError before
the fix and passed after it, with one synthetic read and zero Google traffic.
66 focused tests and independent review passed. Fresh serial original-profile
SDK and registered in-process MCP reads then succeeded on both test profiles,
with matching strictly positive balances. Deployed HTTP MCP acceptance remains
separate until publication. Positive credits do not establish every model's
availability or identify the cause of earlier quota/access or WAF refusals.


Integration gate result for the credit correction:7,922passed,5skipped,
27warnings,89.88%coverage. One existing virtualized-picker browser test failed
in the parallel run; the exact unchanged test then passed in1.77seconds on an
isolated run. All other mandatory hygiene/docs/mirror/lint/format/types checks
passed. No new duplicate-code block was reported. This records the full-run
failure and isolated recovery rather than claiming a single all-green suite.

Fresh deployed predecessor reads on the newly accepted native Auto image passed
registered MCP lookup, REST native URL/no-store lookup and registered MCP native
download with a decoded1024x1024 image, with zero generation or solver tasks.
The operator helper initially expected a project field that the REST URL-only
contract does not return; that helper was corrected without generation replay.
Native HTTP raw remains video-only; image downloads use the existing verified
SDK/CLI/MCP path.


### R02 fresh lookup and raw image delivery — 4 October 2026

Read-only tests of the corrected remote adapter retrieved fresh native URLs and
validated PNG/JPEG bytes for an uploaded and a generated image on each of pro2
and pro3. Both uploaded images decoded4000x4000; both generated images decoded
896x1200. Every response used no-store. Exact registered image aliases passed
fresh URL and raw reads on both profiles; their local fixture mappings were removed.
The newly tagged native-image-raw BDD passed against the isolated remote REST
service using explicit account/project/media and expected native dimensions.
No Google generation, solver task, cookie import or pro1 browser was used.

The same investigation reproduced REST's identity-only inventory adapter dropping
all typed metadata. The corrected existing-parser merge exposed604 image rows
on pro2 and566 on pro3 (including nonprimary rows), preserving timeline fields
and attached origins. These are returned snapshot observations, not complete
account totals or generation history. Scope/type contradictions refuse.

The selected projects contained no videos, characters or saved-user voices before
fixture checks. A generated-video or saved-user playback result therefore cannot
be asserted from this run. Their typed lookup implementations exist, and earlier
upload/character proofs remain separate historical evidence. Both video allowances
are2/2 and audio previews3/3; none was increased or reset. Unmeasured native union/
workflow variants and arbitrary UseAPI references remain unsupported. R02 stays
unchecked until its required live cohorts are established.

Fresh pro2 CLI lookup and registered HTTP MCP lookup passed on an existing
generated image. The existing tagged character-detail BDD passed with a single
copied-image fixture, fresh reference/thumbnail URLs and owned fixture removal.
No paid generation was requested. This supplies current character read proof,
while unmeasured thumbnail variants and saved-user playback remain open.

R02 publication gate:7,944 passed,5 skipped,27 warnings;89.90% coverage in
219.29 seconds with eight workers. Whole-tree Ruff lint/format and strict
Pyright passed, as did repository hygiene, links, published-doc privacy/mirrors
and council references. The duplication proxy found no new changed-code block.
The initial serial suite was interrupted for the deadline; the completed parallel
run above is the full gate. Standalone Pyright initially selected the wrong
interpreter; the prescribed locked uv environment returned0errors.


### R02 existing-video and alias continuation — 4 October 2026

The read-only wider project search found existing generated/uploaded videos in
pro3, so no new video attempts were needed. Uploaded-video SDK download passed:
4,136,091 bytes, valid MP4,1280x2274. Generated-video lookup was RED on four
existing candidates because native metadata omitted width/height. The corrected
shared codec retains unknown dimensions, and download measures the verified
MP4 rather than inventing them. The tagged native-generated-video lookup BDD
passed:1 passed,2 warnings in12.79 seconds,2,307,253 bytes,720x1280, no generation
or mutation requests. Known metadata dimensions still must match content.

The single additional authorised pro2 saved-TTS trial submitted exactly one
preview after one CapSolver solve. Google returned NativeQuotaError; the test
failed with no accepted output or retry and credits1050 before/after. No further
audio/video generation is authorised. The ledger preserves pro2 audio4 and pro3
audio3. Saved-voice detail/playback and voice-alias live proof remain blocked;
the adapters are implemented, not live accepted. R02 stays unchecked.

Exact registered read aliases now share SDK/CLI/MCP/REST ownership checks.
Unknown/foreign/disabled character alias regression tests prove refusal before
browser opening. Native mutations retain their existing inputs.

The continuation publication gate passed7,970 tests with5 skips and27 warnings
in259.40 seconds,89.84% coverage. Whole-tree Ruff lint/format, strict Pyright,
repository hygiene, doc links, published-doc privacy/mirror and council checks
passed. Independent review GO included18 alias tests and119 focused continuation
tests; unknown/foreign/disabled character mappings refuse before browser launch.
The duplication proxy found no duplicate block intersecting changed code.

Actual exact registered aliases passed SDK, CLI, direct MCP and REST URL/raw
reads for an existing generated image on each active profile and both generated
and uploaded videos on pro3. Generated-video metadata retained null dimensions;
raw retrieval returned the valid2,307,253-byte MP4. Uploaded video returned
4,136,091 bytes. All native REST responses used no-store. The temporary local
aliases were removed without deleting any original native media.

A free copied-image character fixture also passed exact registered-alias detail
reads through SDK, CLI, direct MCP and REST on pro2. Its single image reference
and thumbnail matched. The local mapping and only that owned character fixture
were removed; all original media remained present. No image/video/audio
generation request was made by this character test.


### R02 closure — 5 October 2026

Existing saved-user voice detail/playback now has live proof across SDK, CLI, REST
and registered HTTP MCP, including exact registered voice aliases. The earlier
missing saved-voice fixture limitation is superseded. REST through Mac localhost
returned 200/no-store; playback decoded as 374,444-byte,7.8-second mono 24 kHz WAV.
Explicit account/project and fresh ownership checks remain mandatory. Temporary
local alias cleanup preserved the operator's original voice and sent zero previews.

R02 lookup is complete for the supported owned image/video/character/voice types
and verified local mappings. Unknown vendor encodings fail explicitly. Backend
custom-voice creation remains implemented but Google-rejected with
PUBLIC_ERROR_UNUSUAL_ACTIVITY; its exact cause is unknown. Frontend creation
succeeded with matching payloads, while the 90-second backend experiment was
rejected in 0.45 seconds. Full saved-voice CRUD/binding acceptance remains R12;
account-wide inventory completeness remains R03 and exact contract equivalence
remains R11. See [voice usage and limitations](VOICES.md#existing-saved-voices-verified-lookup-and-creation-limitation).

## R06 operation-specific R12 campaign

5 October: R06 implementation is complete; its
[coverage table](CAPTCHA.md#r06-coverage-and-evidence) distinguishes accepted REST
and queued MCP CapSolver images from unaccepted native operations. R06 used only
existing trials, controlled provider responses and read-only deployed checks;
no new solver task, image/video generation or audio preview was authorized.

Only original pro2/pro3 are candidates. Both two-attempt video allowances are
exhausted; pro1 remains disabled and reserved for UseAPI. Preserve cumulative
private reservations, configured keys and original assets. No cookie transfer,
profile replacement or registration change is allowed. Earlier readiness/budget
snapshots above are historical, not fresh permission or unused allowance.

| Remaining case | Smallest next proof | Additional permission required |
|---|---|---|
| Image CLI / native-reference provider | One existing fresh owned project/reference, one count-one CapSolver request, inspect exact acknowledgement and decoded output | One image submission and one paid solver task for the selected original profile. REST/MCP text acceptance already exists; do not repeat it just for a green matrix. |
| Generic / native reference video | Select one representative cheapest compatible count-one case at a time; retain exact request/output handles and decode output | Fresh explicit video allowance plus one paid solver task per selected operation. Any count2–4 batch needs its own output/credit allowance. |
| Native edit / extension | Reuse one fresh eligible owned source and cheapest compatible model; one submitted operation at a time | One video operation/credit allowance and one solver task per case. |
| Image2K / video promotion | Fresh ownership/model/target proof, one2K or cheapest enabled promotion, measure actual decoded dimensions | One target operation allowance and solver task.4K additionally needs verified enabled entitlement; no Pro entitlement assumption. |
| Saved-voice preview / creation | One short preview, exact audio acknowledgement, then inspect/save that same handle; playback/binding proof separate | One explicit audio preview/creation allowance and solver task; permission for any subsequent paid binding/render and invocation-owned cleanup. |

Before each permission-backed test, read revision/queues, fresh access, model and
project/action/site-key evidence. Reserve exactly the allowed attempt before
submission. Use no retry by default; any confirmed-WAF retry requires a separate
explicit total-attempt budget and matching negative acknowledgement. Solve,
submission, acceptance, rejection and uncertainty must remain separate. Partial,
unknown, cancellation and post-acceptance download/save failures stop; recover
existing handles without generation replay. Stop after one refused operation;
record the exact terminal class and context evidence, then continue independent
read-only cases. No repeated refusal experiment is justified without a concrete
new defect or new authorized distinguishing hypothesis. Google refusal cause and
successful voice cost remain unknown; solver issuance cannot establish either.


## R07 paid acceptance pending — minimal R12 plan

R07 implementation/preparation evidence is complete; its full paid acceptance is
not passed. Reuse browser2K output evidence. Preserve original pro2/pro3 profiles,
keep pro1disabled/UseAPI-only and do not change registrations or copy cookies.

| Additional explicit permission | One bounded test and acceptance |
|---|---|
| One native720p promotion on a measured360p source, video credit allowance and solver task only if provider selected | Fresh account/model/source/target reads; one submission; exact output/workflow handle and decoded1280x720 or720x1280 with inherited aspect |
| One native1080p promotion and its credit/provider allowance | Same single-submission proof, decoded1920x1080 or1080x1920 |
| One provider-backed native image2K upscale plus one solver task | Existing source, exact request binding, acknowledgement and actual decoded dimensions; browser2K need not be repeated |
| One native image4K upscale, separately enabled entitlement, credit and optional solver task | Fresh enabled menu before mint; image enum2; decode/report actual dimensions and quality without guessed fixed edges |
| One native video4K promotion, fresh enabled model/tier entitlement, credits and optional solver task | Source/target proof; video enum3; exact handles and decoded3840x2160 or2160x3840 |

These permissions are absent now; both active video allowances are exhausted and
no entitled4K account/output has been demonstrated. Never consume a solver task
for an unavailable/unknown capability. Retry is off; a confirmed-WAF retry needs
its own explicit total-attempt allowance. Accepted/partial/unknown work and later
validation/download failures retain handles and stop, without replay. Fixture
upload/cleanup uses only a clearly identified invocation-owned source if needed;
original assets remain untouched.


### R08 supported reference closure — 5 October 2026

The existing weighted budget/composer implementation is retained. Supported
Python/CLI/direct and queued MCP/REST image references use current model metadata,
fresh ownership, separate image/character pools and actual character image weights.
Mixed local/native slot order and positional prompt markers survive request/queue
preparation. SDK/queue/MCP now refuse boolean/fractional counts and explicit invalid
model/aspect choices; model/count/seed/aspect forwarding has controlled coverage.

Fresh Mac-localhost REST/MCP reads on original pro2/pro3 agree: Nano2/Pro/Lite
have ten effective image slots and seven effective character slots. Original-library
zero-generation BDDs passed one each (pro2 34.00s; pro3 24.80s), preparing all three
models with ten existing ordered native images, count2, seed42 and explicit3:4,
then stopping at a substituted transport before real mint/submission. Missing
references refused and first-native-reference Auto used the documented policy.
No usable active character fixture existed in either selected library; actual
one/two-image weights, zero/smaller character pools and weighted overflow have
controlled fixture coverage. No original resource was changed or copied.

Focused interface/budget/Auto/worker group: 258 passed in21.76s. Controlled SDK,
MCP and daemon group: 60 passed in12.97s. SDK control regression went RED14failures
then GREEN15; MCP control regression went RED5failures then GREEN8. A temporary
queued worker preserved ten ordered references, model, aspect, count and seed,
then stopped with may_have_spent=false; no production job was enqueued.
Required release gate: 8,123 passed, 5 skipped, 27 warnings in256.97s,
89.94%coverage. Hygiene, links, published privacy, generated mirrors, council
references, Ruff lint/format and strict Pyright passed. Duplication proxy found
only existing blocks in untouched code. No repeated whole-suite run was needed.
Post-review documentation/mirror and surface-schema checks are recorded in the
R08 handoff.

Reused accepted ten-reference evidence is original-pro2 Lite count-one SDK with
canonical slots, on source baseline890a65918255d5a71065a82af0e0bd61a404c2b0 plus
composer corrections committed as a7846083edfeb61861bb8c5f8cf23d2af3215cb7.
The corrected retained follow-up records ten identities in order, captured1,
dispatch1, accepted1, fresh owned output and a decoded768x1376JPEG, clear10to0;
fixtures were archived and originals preserved. An earlier separate output was
recovered read-only after an output-path mismatch, without replay. This supersedes
historical statements that ten-reference rendering was wholly unverified. It
proves ordered attachment/request preparation and an accepted Lite output, not
visual influence of each reference or all wrapper/model rendered coverage.
Native Google Auto remains distinct from the first-reference approximation.
See [R08 forms, limits and scope](IMAGE_REFERENCE_BUDGETS.md).


## R11-based R12 permission checklist

R11 authorized no production generation. The user subsequently authorized the
separate R12 allowance and invocation-owned fixtures on 5 October; the measured
results above supersede this preparation checklist without resetting history.

- [x] Obtain new per-operation attempt/credit/solver caps on original pro2/pro3;
  historical usage stays separate. Keep pro1 disabled/reserved.
- [x] Choose a small representative output campaign: REST Auto/mixed grounding;
  queued MCP/REST generic plural video; native reference/edit/extension with
  requested Fast/Lite/Quality family where currently available. Each has separate
  accepted/refused/unknown evidence and no blind replay.
- [x] Obtain explicit paid promotion/image upscale permissions; prove720p/1080p
  target pixels and entitled4K only when fresh catalogs actually offer it.
- [x] Obtain bounded voice preview/create/binding permissions if that backend
  acceptance gap is to be tested; reuse existing saved playback evidence.
- [x] Authorize creation and cleanup of invocation-owned temporary assets only
  for any missing mutation lifecycle proof. Preserve every original asset.
- [ ] Specify a public allowlisted callback receiver for actual delivery proof;
  controlled callback/recovery outcomes already cover R11 semantics.
- [x] Record fresh account/model/credit reads and reserve the private ledger
  before each allowed attempt. Stop at accepted/unknown/refused budget limits.

Automatic renewal remains the separate R10 acceptance boundary. Cookie import,
profile replacement and pro1 testing remain excluded. No numerical generation
seed investigation or vendor-wide statistics work is proposed for R12.
