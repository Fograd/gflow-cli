# Self-hosted fork verification

Measured across 2026-10-02–03 using one authenticated Google AI Pro profile served by `flow.google.com`. Previously published snapshot: one/two-reference character creation, initial notes and system preset assignment are live verified through the native adapter. Native MP4 upload and reversible archive are verified separately through SDK, CLI, registered MCP and HTTP below. The preceding portable-media offline gate was 5,612 passed, 28 skipped and 90.75% code coverage. This is code coverage, not useapi feature completeness or Google generation success. Earlier gate results below describe their recorded historical snapshots.

| Surface | Evidence | Result |
|---|---|---|
| CLI native image 2K | Existing 1376×768 JPEG → 2752×1536, 3,334,707 bytes | Passed |
| Shared-client/MCP native image 2K | Three real-profile BDD cases, including Pro 4K refusal |3 passed |
| HTTP native image 2K | Durable job completed, inline JPEG 2752×1536, 3,334,707 bytes | Passed |
| Tee client text-to-image | Existing tee client used the local endpoint and received 458,359 bytes, 1024×1024 | Passed |
| Raw upload and reference generation | Existing tee request format produced blue mug variation from red source, 271,282 bytes | Passed |
| HTTP complete image workflow | Real HTTP BDD: generate → upload → reference generation → native 2K; asserts exactly doubled dimensions |1 passed in 133.91 s |
| Actual Streamable HTTP MCP upscale | Live tool call through the running service returned native 2K bytes after direct detail navigation fixed gallery virtualisation | Passed |
| Authentication | HTTP 401 without bearer on REST and MCP; authenticated MCP lists 18 tools including both upscale tools | Passed |
| Native HTTP seeded image batch | Two requested consecutive seeds 12042/12043 returned by Google, two decoded images at least 1024 pixels |1 BDD passed in 29.44 s |
| Native MP4 resources | Synthetic one-second MP4 upload with explicit per-upload rights confirmation, native selected-project list and reversible batch archive; no generation credits | Native worker BDD 1 passed in 32.07 s; HTTP REST BDD not performed |
| Initial offline regression | 4,911 passed, 30 skipped; 91.26% coverage; one README sponsor-placement failure | Placement corrected and targeted test rerun |
| Expansion offline regression | 4,960 passed, 49 skipped; 88.18% coverage; three environment/marker failures | Added missing resource BDD tags, restored uv PATH; 142 focused tests passed; final targeted gates recorded below |

The one real-profile native-upscale BDD run had a profile contention/setup failure while another test was using the account. It was repeated without concurrent browser work and all three cases passed. Profile leases rejected contention safely; no browser was killed.

## Explicit limits

Only one of the user's three Pro accounts is authenticated and configured for execution. Successful 4K cannot be tested without an Ultra account; Pro 4K refusal is verified. The three plans are independent allowances, not an Ultra entitlement.

At the original export-adapter checkpoint, no video generation credits were spent. Native video 1080 p/original 720 p/GIF export adapters have offline coverage, but no existing Google-generated video was available for live validation. Other unsupported controls and endpoints are listed in [the compatibility inventory](PARITY.md). API presence is not proof of full useapi parity.

Tee's production provider was not switched. Its existing client was exercised against the new endpoint by overriding its base URL in an isolated verification process. The local service and fork can be used independently of that production configuration.

CAPTCHA provider configuration and token hooks have offline coverage. Actual Google acceptance remains unverified despite the later paid CapSolver trial below. Earlier JavaScript metadata hooks failed; the later native reload parser supersedes them. Neither metadata nor key storage is successful live solver acceptance.

The expanded service was restarted with no active jobs. Authenticated capability discovery and provider configuration returned HTTP 200; unauthenticated capability discovery returned HTTP 401. Video generation remains disabled.

The main-world and early-hook CAPTCHA probes were aborted before Google submission and still returned no action metadata. Those historical probes were superseded by native reload capture below. Provider generation continues to return HTTP 501 pending actual third-party acceptance; key configuration remains usable. Final focused API/transport/MCP verification:157 passed.

Final complete offline regression (with corrected marker/PATH setup): **4,969 passed, 47 skipped; 90.36% coverage** in 208.80 seconds. Whole-tree Ruff format/lint and strict Pyright passed; documentation links, repository hygiene, website privacy/mirror and council-memory checks passed. Duplication proxy found only pre-existing experimental/CLI-MCP mirrors.

A bounded ten-image reliability pilot returned nine images across four submissions, with no explicit CAPTCHA refusal observed. One four-image batch returned three; a diagnostic repeat returned four. The test found and corrected REST partial-count completion handling. See [the full evidence and limits](STRESS_TEST.md).

Post-stress reporting-fix regression:4972 passed, 47 skipped; 90.39% coverage. 94 selfhost tests passed, including short/exact/excess result counts and preserved assets. Whole-tree lint/format and strict types passed.

Native CAPTCHA reload parser passed three abort-only metadata probes (IMAGE_GENERATION action and trusted-query-matched site key), superseding the earlier failed JavaScript hook. Fresh same-page TokenMinter replacement BDD submitted but Google rejected unusual activity (WAF 403/gRPC 7); no image was accepted. This is not successful CapSolver or external-token acceptance; provider generation remains disabled with HTTP 501.

Actual paid CapSolver trial: solveStarted 1 / solved 1 / submitted 1 / accepted 0; one replacement submit rejected PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7/HTTP 403), no retry. Provider generation remains disabled with HTTP 501. CLI/SDK/MCP/queued seed support now has offline parity and a callback-context regression fix; the corrected CLI path later produced one accepted native image with actual seed 42, JPEG 1024×1024 and 397,336 bytes, without a solver or retry. The successful REST seeded batch above is a separate proof and does not establish CLI/MCP live seed verification.

Corrected CLI seed proof: one native submission returned seed 42 and a 1024×1024 JPEG (397,336 bytes), no solver and no retry. MCP/queued seed paths have offline parity; this CLI result does not claim separate live MCP verification.

Native account project paging was measured through UpteDb: two pages of 21 entries with disjoint project IDs and opaque continuation. The adapter exposes explicit source=google; useapi history aggregation remains unported.

Deployed native HTTP catalog BDD: **1 passed in 33.03 seconds**, with no generation or solving. It verified two disjoint native account project pages, project-scoped character summaries and dynamic system voices. Earlier observations measured 42 distinct projects across two pages and 30 system voices. Character lifecycle proof and the latest stable full regression were subsequently completed below.

Native character adapter proof passed without generation: create draft, copy an existing owned image into it, observe visible project catalog, update name/personality and delete. The source stayed active and copied workflow differed; probe characters were cleaned up. The deployed HTTP CRUD BDD later passed as recorded below. Initial personality-on-create is implemented through a validated post-copy update; the subsequent two-reference proof below supersedes this one-reference snapshot; voice assignment was unsupported in that historical snapshot; the later preset-assignment proof supersedes this limitation. Initial-personality HTTP CRUD is live verified.

Deployed HTTP character CRUD BDD: **1 passed in 91.94 seconds**, without generation or solving. It created a character by copying an existing owned image with initial notes, PATCHed notes, GET-verified stored references/notes, DELETEd it, confirmed HTTP 404 and verified the source image remained active. All test entities were cleaned up. This proves the one-image metadata flow. The later two-reference proof below expands it; voice assignment was unsupported in that historical snapshot; the later preset-assignment proof supersedes this limitation.

Previous one-reference publication gate: **5,085 passed, 47 skipped; 90.44% coverage**, in 223.54 seconds. Ruff checked 570 files cleanly and strict Pyright reported zero errors. Tracked repository hygiene, documentation links, privacy/mirror and council checks passed; staged private-identifier and actual CapSolver-key scans were clean. This gate covers the published implemented scope, not complete useapi parity. At that recorded snapshot, second-reference work was still a spike; the later completed gate below supersedes that limit.

Two-reference native adapter BDD: **1 passed in 34.11 seconds**. Deployed two-reference HTTP lifecycle BDD: **1 passed in 97.82 seconds**. Both references were validated atomically before creation, copied into measured portrait slot 0/body slot 1, persisted, and both source images remained active; the owned test entity was removed. The shared post-create deadline remains 45 seconds. The final second-reference gate passed as recorded below.

Second-reference stable offline gate: **5,098 passed, 47 skipped, 15 warnings; 90.56% coverage**, in 219.93 seconds. Strict Pyright reported zero errors and Ruff checked 571 files cleanly. Duplication checks found only the same three pre-existing unchanged findings. The manual six-axis CLI surface check is not applicable to this change: it extends REST/worker adapters without changing CLI commands. Post-staging hygiene/privacy checks are recorded by the publication step.


Guarded native voice-picker probes: **two owned fixtures created and cleaned up**,
with no TTS/image/video generation or solver submission. Charon was selected with
empty dialogue/performance, but the preview-pane button candidate was not verified
as the add action. The first authoritative audio slot was null; the second picker
remained open and its backdrop blocked header Done. No committed native voice
metadata update was observed. Unknown `WuwhI` requests were aborted without
classifying their purpose. This result is **inconclusive for Google voice support**
and does not enable REST assignment/custom voices. Read
[the redacted transition evidence](../superpowers/spikes/2026-10-02-native-voice-picker-transition.md).

## Native preset assignment (current expansion)

The native adapter BDD passed **1 test in 65.12 seconds**, without generation or
solving: two copied existing references, initial notes and Charon assignment,
Aoede update, fresh metadata reads and owned-character cleanup. Both original
source images remained active. This verifies persisted system preset assignment,
without a rendered speech or generation-binding claim. CLI/MCP use the same
native SDK/service but need their separate surface proof.

## CLI/MCP first lifecycle run (diagnostic result)

The new actual CLI subprocess and registered MCP tool scenarios created two
existing-reference characters with initial notes and Charon successfully. Their
notes-clear updates then returned typed unknown mutation outcomes, so the full
run was **2 failed in 140.73 seconds**. Both owned entities were removed in test
teardown. This diagnostic exposed a native clear acknowledgement/persistence
mismatch; it is not a successful surface lifecycle proof. The native owner is
repairing and remeasuring it before a complete rerun. No generation or solver
was invoked.

## Native notes-clear repair

The native owner repaired the clear-field wire representation and fresh-read
normalization: empty personality is represented as absent/`None` in the returned
DTO. The adapter BDD passed **1 test in 69.90 seconds**: notes cleared while the
name, Charon preset and two copied references remained intact, followed by owned
entity cleanup. This supersedes the native limitation exposed by the first
CLI/MCP run; the separate surface lifecycle rerun is in progress.

## Actual CLI/MCP native surface proof

The surface rerun passed **3 tests in 265.40 seconds** (2 warnings). The tests
invoked the actual CLI subprocess and registered MCP adapter independently,
using existing, active, locally verified native references:

- Each character surface created two copied references with initial notes and
  Charon, listed/read the entity, cleared notes, renamed/set new notes and Aoede,
  read persisted metadata, then removed its exact owned identity.
- CLI/MCP native project inventory returned matching IDs across two disjoint
  pages using the opaque cursor. Their media snapshots agreed on native image/
  video identities and kinds, reported `complete: null`, and omitted signed URLs.

All owned character fixtures were cleaned. No generation or solver was invoked.
The first notes-clear failure above is superseded by this successful surface
rerun. The SDK inventory scenario was deselected by its different cost tag in this
combined run. Its explicit strengthened rerun then passed **1 test in 11.42
seconds** (2 warnings), requiring 21 + 21 disjoint project rows, a nonempty
opaque cursor, mixed native image/video kinds and dimensions, unknown
completeness and omitted signed URLs. This is a separate SDK proof.

## Deployed HTTP preset and notes-clear proof

After restarting the API and MCP services on the current source, the deployed
HTTP character lifecycle BDD passed **1 test in 123.99 seconds**: create two
copied references with initial notes/Charon, PATCH Aoede/new notes, GET persisted
metadata, clear notes, GET confirm preserved Aoede/two references, DELETE/404,
and confirm both original sources remain active. The owned fixture was cleaned.
No generation or solver was invoked. This expands the earlier HTTP proof with
preset assignment and repaired notes clearing.

## Base wheel runtime dependency regression

A fresh base wheel installation initially failed before any command parsed:
CLI imports the shared native character service, whose image verification needs
Pillow; Pillow had previously been optional. The dependency was promoted to core
and the lock regenerated. The actual fresh built/installed wheel documentation
integration then passed **2 tests in 3.08 seconds** with no checkout fallback.
The effective base-plus-chain dependency test retains bounded Pillow and PyAV
requirements; all **26 chain tests passed in 0.69 seconds**. `uv lock --check`
passed. This verifies a real base installation rather than relying on a developer
machine's optional dependencies.


## Publication gate — 2026-10-03

Final complete offline regression: **5,220 passed, 47 skipped, 15 warnings;
90.71% code coverage**, in **218.95 seconds**. Coverage measures exercised code;
it is not Google generation success or useapi feature parity. Whole-tree Ruff
checks and formatting (588 files), strict Pyright (zero errors), repository
hygiene, documentation links, published privacy/mirror/navigation and council
memory checks passed. The duplication proxy reports two unchanged experimental
transport blocks; the touched local CLI/MCP project duplicate was extracted.

Fresh built/installed wheel verification passed **2 tests in 3.08 seconds**;
Pillow is now a declared core dependency for native image-reference validation.
The chain dependency suite passed 26 tests and the lock check passed. A
header-valid truncated JPEG is rejected before browser allocation: verification
now checks both file integrity and actual pixel decoding. Two existing private
catalog references also passed this local check without accessing Flow.

Independent review found and corrected a populated human project-list key
mismatch, character Rich rendering of literal user metadata, and loss of known
deletions when a later batch target is refused before mutation. Exit 40 preserves
unknown mutation identities or known completed references with the distinct
partial-batch problem type; no mutation replay was added. Image recovery spans
CLI, REST, queued MCP and batch failures/restart, preserving known handles and
completed files. Callback responses are streamed and closed without reading
their bodies; the existing DNS pinning, HTTPS, allowlist and attempt limits remain.

Manual six-axis surface review:

| Axis | Result |
|---|---|
| Execution paths | Native metadata/inventory use shared SDK services through direct CLI/MCP; CRUD has no replayable queue. Image recovery covers direct, REST, queued and batch callers. |
| MCP truth | Native create/update/remove and project/media parameters match their CLI mirrors; explicit deletion confirmation and unknown completeness are documented. |
| Agent surfaces | README, AGENTS, llms, index and both shipped gflow skills describe the new commands and the older portrait-generation exception. |
| Errors | Exit 40 distinguishes unknown writes from confirmed partial deletion. First preflight refusal remains configuration error; recovery errors are nonretryable. |
| Declarative surfaces | No new operator setting for native metadata/inventory; the recovery invocation variable is internal. Runtime dependencies and lock are consistent. |
| Docs/mirror | CLI/MCP usage, character guide, API, surface matrix and compatibility inventory updated; deployment-specific guides stay in fork documentation. |

Only pro1 was used. All owned character fixtures were cleaned up, both source
images remained active, and this expansion submitted no image/video/TTS
generation or solver task. Full useapi parity remains open in the compatibility
inventory; accepted CapSolver generation is still guarded.

Authenticated deployed REST capability discovery passed (401 without bearer,200 with bearer). The restarted Streamable HTTP MCP service exposed22tools, including native create/update/remove and project/media tools, through actual protocol initialization/listing. No generation tool was called during registration verification.


## Isolated reference expansion: measured checkpoint

The native SDK canonical image BDD passed one case in 104.75 seconds: original literal spans, repeated media chip positions, one owned character, deduplicated vectors and fresh weighted ownership checks. Exactly one dispatch produced a square 1024×1024 JPEG of 270277 bytes. The owned character fixture was removed. The abort-only guard proof passed separately; no broad video positional-grounding claim follows.

A separate free sequential SDK/CLI/registered-MCP native voice discovery proof passed in 27.05 seconds. All three surfaces returned the same 30 preset names and unknown completeness. It performed no generation and no mutation. This verifies dynamic preset discovery, not rendered voice application.

Offline parser, weighted preflight, slot codec, CLI/MCP, voice and HTTP boundary checks passed 81 cases in 19.66 seconds. A broader HTTP server/reference check passed 97 cases in 3.72 seconds; duplicate logical body aliases and typed aspect mapping were then verified by 11 focused tests. Generated skill and website mirrors, published PII checks and 219 tracked-document links passed. Full checkpoint regression is recorded by the coordinator after all source is frozen.

## Restored session and queued health proof — 2026-10-03

Google required a human identity challenge while the saved account remained
available. The cause was not established. After the user completed it in the
original hosted profile, repeated context closures/reopenings preserved actual
project access. The canonical image BDD passed with one accepted image as
recorded above; no repeated login was needed during subsequent free voice reads.

The new health helper returned OK/project_access_verified with profilePreserved
true and refreshAttempted false. An isolated real HTTP queue service on CC LXC
then passed unauthenticated401, asynchronous201 and completed project-access
verification. It used the existing account and generated nothing. This is actual
HTTP/worker/native proof; production-service smoke verification is separate.
Cookie transfer acceptance and permanent prevention of Google's identity checks
are not established by these results.

## Canonical reference and session-health publication gate — 2026-10-03

Final frozen-source offline regression: **5,495 passed, 28 skipped, 15 warnings;
90.62% code coverage**, in **238.49 seconds**. Coverage measures code exercise,
not generation success or useapi parity. Whole-tree Ruff check/format left 628
files unchanged; strict Pyright reported zero errors. Hygiene, 219-file links,
26-file published privacy guard, 21-file website mirror/navigation and council
memory checks passed. The staged private-value scan found zero matches.

Independent reviews covered the pinned staged tree and final corrections.
They found and fixed importer FIFO blocking/engine mismatch and cleanup safety,
HTTP alias-to-aspect translation, repeated logical-reference aliases, error
taxonomy test construction, and project loss after an interrupted image
submission. Six additional URL-change/closed-page fault cases preserve the pinned
project and known handles; cancellation remains cancellation. No HTTP ownership
check was loosened.

Six mirror axes were reviewed: CLI/direct-MCP/queued-codec/HTTP preserve immutable
canonical image plans; preset catalog flags match SDK/CLI/MCP; source and shipped
agent skills and website mirrors agree; image uncertainty uses safe nonretryable
exit40; HTTP wait defaults and capability discovery distinguish local Auto from
native Auto; cookie secrets remain private with a justified CLI-only credential
import surface. Successful cookie transfer and provider-token acceptance remain
unproven. Actual CLI/MCP/HTTP canonical-image acceptance is tested separately from
the successful SDK proof; it is not implied by this offline gate.

The original hosted profile remained reusable after manual identity verification.
The new health action is on demand and serialized, not a periodic login refresh.
Publication and production-service smoke are recorded after deployment.

## Published deployment and production session check

Checkpoint fd56b2e6 was published to the fork's develop and self-hosted feature
branches and deployed by a clean fast-forward on CC LXC. Both API and MCP services
restarted; the queue was idle and the original profile lease was available.
The additive account schema upgrade preserves existing registration and history.

The production HTTP health proof passed: no bearer401; updated authenticated
capabilities; async201; completed OK/project_access_verified with the original
profile preserved and no refresh. The authenticated registered MCP protocol
exposed22tools and the new image-reference/native-voice parameters. No generation
or solver operation was invoked by these checks. A test-client mistake (missing
MCP bearer and assuming the older three-stream tuple) was corrected in the
private smoke client; it required no product or account change.

## Portable native MP4 upload/archive acceptance — 2026-10-03

Four opt-in real-browser BDD runs passed individually against the original saved
profile: SDK54.80s, public CLI57.56s, actual authenticated registered MCP67.96s,
and HTTP51.86s. Each uploaded one owned synthetic one-second MP4 and reversibly
archived only that new fixture. Fresh native reads verified every original active
media identity remained active. No image/video/TTS generation or solver task was
part of these operations, and no upload or archive was automatically replayed.

MCP used the actual Streamable HTTP protocol against an isolated new-source
server. HTTP used a fresh private durable queue, with exactly one completed assets
job and one completed assets/archive job. An initial private HTTP test bootstrap
used the wrong URL prefix and returned404; its database had zero jobs. Its logs
and allowance were retained, and the corrected proof used a separate allowance.
No production account or source mutation was needed to correct that test client.

Independent review reproduced and fixed two cleanup holes: a listener-removal
failure after upload acknowledgement could lose its known media ID, and a file
descriptor close failure could hide cancellation and skip snapshot cleanup.
Known handles now survive these secondary failures; cancellation retains its
identity and typed private recovery metadata. Strict registered MCP booleans
refuse integer/string coercion before the service is called.

Archive proof is for the measured singleton upload workflows. Fresh membership
checks fail closed for missing or ambiguous siblings; this does not establish
every possible multi-output batch or individual permanent-deletion compatibility.
Native video generation, export promotion and speech remain separate proof
obligations. The original login was reused throughout without another manual
identity challenge; permanent prevention of Google's security checks is not
claimed.

## Portable media publication quality gate

Final frozen production source and offline-test regression: **5,612 passed,
28 skipped, 15 warnings;90.75% code coverage**, in **212.90 seconds**. Code
coverage does not measure Google acceptance or full useapi compatibility.
Whole-tree Ruff and strict Pyright pass. The first sweep found an old error
taxonomy test using a free-form positional constructor for every class; it now
constructs the new recovery error with validated keyword fields. Product error
validation was not weakened. Focused taxonomy checks and the full rerun pass.

Independent source and documentation reviews covered shared SDK/service
operations, strict registered MCP consent, CLI/worker/HTTP projections, bounded
private snapshots, whole-batch ownership and secondary cleanup faults. The HTTP
test initially failed to checkpoint its final archived flag; its final native
read and completed durable archive job had verified the operation. The test now
checkpoints immediately after acknowledgement. The private original checkpoint
was preserved and any later correction explicitly labeled post-run verification.
No mutation was replayed to repair an evidence file.

Six mirror axes: CLI and direct MCP share validated native operations, while REST
uses the durable serial worker; these mutations have no replayable MCP queue.
Registered signatures and docs require explicit per-request confirmation. README,
AGENTS, indexes and both agent-skill copies describe the commands. Safe exit40
taxonomy and HTTP known/pending identities match usage docs. No normal operator
environment setting was added. CHANGELOG, canonical docs and website mirrors
describe the stricter MP4 consent contract and measured scope.

The duplication proxy found only two unchanged experimental transport blocks.
Fork publishing and production deployment are recorded separately after their
actual completion; no remote CI or Sonar result is inferred from these local gates.

## Portable media publication and production smoke

Source checkpoint c03c1fe3 was atomically published to the fork's develop and
self-hosted feature branches, with both remote references independently checked.
CC LXC deployed it by a clean fast-forward with idle API/MCP queues and the
original profile lease guarded. The pinned lock synchronized successfully;
both API and MCP services restarted active.

A fresh production health job (not the earlier cached idempotent proof) completed
OK/project_access_verified with profilePreserved true and refreshAttempted false.
Unauthenticated capabilities returned401; MP4 without per-request rights returned
the specific consent422 before queueing. Actual authenticated Streamable HTTP
registration exposed24tools and both native upload/archive input schemas. These
smoke checks performed no generation or solver operation.

## Final native feature batch — 2026-10-03

The batch adds standalone video extension, Omni video editing, image/saved-audio
reference video, saved TTS voice CRUD and character binding, permanent individual
media deletion, local-reference Auto image aspect and native credit reads.
SDK, CLI, MCP and durable REST adapters are wired. Registered MCP exposes35tools,
up from24. Availability and offline coverage do not establish accepted generation.

| Final live check | Measured result |
|---|---|
| Native reference/audio model catalogs and credits |1passed; observed model IDs and a nonnegative native balance |
| Native extension/edit catalogs |1passed; observed native model IDs |
| Synthetic MP4 upload and permanent selected-media deletion |1passed/4skipped in28.91s; all original active media retained |
| Native image-reference video with browser token |1failed; one request received PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC7; no accepted output |
| Controlled CapSolver native image-reference video |1failed/4skipped in25.84s; one Enterprise-v3-proxyless VIDEO_GENERATION solve, one submit, one explicit Google refusal; no retry or accepted output |
| Corrected canonical-preset TTS preview |1failed/4skipped in17.93s; captured no0P6 returned PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC7; no accepted audio or binding lifecycle |
| Auto image through CLI |1failed/4skipped in54.38s; shared composer returned FlowAgentUiError, exit25; no accepted image or resolved-output proof |

The first TTS preview had an ambiguous outcome and no acknowledged handles.
A source inspection corrected canonical preset capitalization; the later captured
request proves an explicit refusal rather than establishing the earlier cause.
The first individual-delete check observed a valid acknowledgement before the
timeline propagated. A later metadata-only read confirmed removal, and the final
passing BDD polls bounded reads without repeating deletion.

Final tests used separate private temporary directories. A preparation error
pointed a provider test at an empty profile; it failed before solving or Google
generation. Its checkpoint remains separate from the measured authenticated
CapSolver trial. An earlier private plugin import error also submitted nothing.

Across the earlier image trial and this video trial, the private ledgers show2solved,
2submitted,0accepted and2rejected operations. API counters remain scoped to their
self-hosted instance and do not retroactively aggregate separate manual trials. A solved token is not Google
acceptance. Provider-backed public generation remains guarded; keys, tokens,
signed URLs and raw captures remain outside Git. No additional extension/edit
generation or rendered-audio reference request was sent after the same-account
Google refusals. Those paid acceptances remain externally blocked and unverified.
Auto MCP acceptance shares the unresolved composer boundary and is unverified.

Typed known WAF/content refusals now project safe nonretryable HTTP403/400 errors
without outcomeUnknown; genuinely ambiguous mutations retain exit40 and known
handles. Only one profile has been tested. Existing native image2K proof remains
separate from the new blocked generation tests.

Six surface mirrors were checked: public CLI/direct MCP/queued Auto payloads,
registered schemas and parameter docs, agent-facing indexes and skills, typed
errors and HTTP projection, declarative defaults, and canonical/website docs.
New video mutations use separate durable workers with pre-dispatch checkpoints.
No native Google AUTO enum, ten-image budget, numerical video seed or full useapi
equivalence is inferred. See [the complete remaining inventory](PARITY.md).

## Final feature-batch quality gate

The final broad offline sweep returned5,763passed,5skipped and88.63% coverage
in288.76seconds, with one website-mirror synchronization test failing while
canonical docs were still being finalized. Mirrors were then regenerated and the
failed gate rerun against the frozen documents:83focused tests passed, including mirror synchronization, CLI/MCP parity, native workers and refusal projection. Strict types, whole-tree lint and
format, repository hygiene, doc links, website privacy/navigation and council
memory checks are separate publication gates. These measurements describe code
and docs; they do not override the explicit live generation refusals above.

The duplication proxy identified the existing experimental transport mirrors and
one new worker checkpoint block. The new extension/edit duplicate was extracted
into a shared writer, preserving filenames, recovery fields and mode600.
The focused worker regression passed after this small source change. No extra
generation or solver request was used for these corrections.

The frozen feature baseline then passed the complete offline suite:
**5,764passed,5skipped,15warnings;88.63% coverage**, in243.56seconds.
Actual authenticated staged HTTP reads returned5extension models,2edit models,
13reference models and an empty saved-user-voice catalog. Actual Streamable HTTP
registration returned35MCPtools. These reads perform no generation or solving.
An initial staging client used an unsupported profile query parameter and
received501 before browser work; the corrected client used the documented email
selector. This was a test-client correction, not a server feature failure.

## Final review response-contract corrections

The pinned baseline review found two public result defects: successful saved-TTS
job responses dropped the new voice IDs, and uncertain voice/video failures
dropped public recovery IDs. Narrow route/shape-specific projection now preserves
acknowledged UUID identities and bounded voice metadata through synchronous
delivery, polling and callbacks. Invalid, foreign-project and private fields
remain excluded; explicit Google refusals stay distinct from uncertainty.
The focused HTTP outcome regression returned51passed.

MCP extension/edit/reference also now write invocation-specific private started
journals before dispatch and retain typed output identities if playback/download
fails. Missing URL, download failure and cancellation cases across the three
tools returned13focused passes. Cancellation still propagates. These corrections
required no new generation or solver call. Private council-memory slugs were
unavailable to reviewers; that limits memory-history review rather than live
generation proof. Source and public spike/verification records were reviewed.

The final changed HTTP/MCP/worker domains and mirror regression returned
**770passed in44.06seconds** after the review corrections. Whole-tree Ruff,
format verification and strict Pyright were clean on those final source changes.
No accepted video/TTS output or full vendor parity is inferred from these gates.

## Native feature publication and production smoke

Feature source357f5e56 was atomically published to the fork's develop,
feature/self-hosted-flow-api and feature/useapi-parity-2026-10-03 branches.
All three remote references were independently checked. CC LXC production source
fast-forwarded cleanly with empty accepted/running REST and pending/processing
MCP queues. Locked dependencies synchronized and API/MCP restarted active.
The existing profile and private provider keys were preserved.

The production video API was explicitly enabled behind its existing bearer
authentication. Unauthenticated REST capabilities returned401; authenticated
capabilities returned200/videoEnabled=true, account and provider configuration
reads returned200, and native extension discovery returned5models. Saved-user
voice inventory returned200 with0voices. Actual production Streamable HTTP MCP
registered35tools, including all new generation and selected-delete tools.
These deployment probes generated no media and created no provider tasks.

A first production probe mistakenly targeted loopback despite the configured LAN
listener and failed at connection before any request. The corrected probe used
the existing LAN binding. Temporary staging API/MCP services were then stopped;
the production API, MCP and CapSolver key GUI remain active.

Council review closed the public voice identity and uncertainty defects at
357f5e56. Correctness, tests, CLI/surface parity, security and documentation found
no remaining concrete publication blocker. Live acceptance remains conditional:
Google refused video/TTS, and the Auto CLI composer gate failed. The external
acceptance warning is retained rather than described as a green rendered-output
proof. Private memory-history review was limited; source/public evidence and the
mechanical public memory gate were checked. Publishing adapters does not establish
complete useapi parity or acceptance across three accounts.

## Owned native image Auto sizing

The read-only native UUID Auto BDD passed once in 7.68 seconds on the existing
authenticated profile. One fresh owned typed image measured1024×1024 and resolved
to1:1 with the same requested/resolved/policy fields. The test forbids image
generation; no upload, mutation, CAPTCHA task or credit-consuming render was made.
The resolver now supports CLI and direct/queued MCP before queueing, and the SDK
helper. Managed REST images retain byte-derived sizing; unregistered remote UUID
lookup is a separate gap. This proves sizing against real metadata, not acceptance
of an Auto generation through the currently blocked composer.

## Automatic native video edit end

The read-only duration BDD passed once with two warnings in8.22seconds. Fresh
owned typed-video metadata supplied a one-second duration; omission resolved to
end24 at virtual24fps. No edit dispatch, download or solver call occurred.
Source-derived duration parsing, omission through SDK/CLI/MCP/REST, explicit
overrides, invalid-before-mint refusal and public frame-result filtering have
focused regression coverage. This proves source-length/default-window behavior,
not accepted edited-video rendering.

The final offline suite passed5849tests with5skips and15warnings in175.56seconds,
with88.95%coverage. Whole-tree Ruff/format and strict Pyright were clean. The first
sweep exposed an obsolete CLI required-end test and a missing live-feature tag;
both were corrected, including optional/explicit CLI parameter propagation.
The duplicate-code proxy found only unchanged experimental transport duplicates.
Public source and published-doc privacy checks found no private keys or fixtures.

## Owned-media batch publication and deployment

Source9442e653 was atomically published to the fork's develop,
feature/self-hosted-flow-api and feature/useapi-parity-2026-10-03 references;
all three remote SHA values matched. With zero queued/running REST or
pending/processing MCP jobs, production CC LXC source fast-forwarded cleanly,
locked dependencies synchronized and API/MCP restarted active. The CapSolver
GUI remained active; private provider keys and the saved browser profile were
preserved.

Production unauthenticated capabilities returned401; authenticated capabilities
returned200 withvideoEnabled=true. Native edit-model discovery returned200/two
models. A real authenticated MCP session listed35tools, confirmed end_frame
absent from the edit tool's required schema, and confirmed its image tool exposes
native-image UUID Auto sizing. These probes generated no media or solver tasks.

## Expanded agent panel recovery investigation

On2026-10-03, an authenticated zero-submit DOM probe observed the classic
settings trigger present but hidden and the mode chip absent while chat was
expanded. Opening the tune control showed the image model/aspect/count settings.
Closing the unique visible agent-panel header close remounted a pressed mode chip.
Closing alone left classic settings hidden; the subsequent pressed-chip toggle
restored them. The old recovery checked the chip before closing the panel and
therefore prematurely returned absence. This is a recovery-order defect, not proof
that the account has no classic composer or needs another subscription.

The new real-CSS regression failed first (absent instead of clicked), then passed
with the bounded close/reprobe implementation. The tagged live no-submit BDD passed
once with two pytest deprecation warnings in15.21seconds. It proved restored
classic settings and zero observed generation requests. An initial harness attempt
intercepted binary network bodies and failed in request decoding; the guard was
restricted to batchexecute. A second attempt sampled before the asynchronous chip
removal settled; the scenario now waits for the measured detach transition.

The focused composer suite passed144tests in37.21seconds. The full offline gate
passed5855tests with5skips and15warnings in181.22seconds, with88.96%coverage.
Whole-tree Ruff/format and strict Pyright were clean; CLI/MCP parity gates
passed61tests. Private-value scanning found zero staged keys or live fixture IDs.

Source64974ba0 was published atomically to all three fork references, then
fast-forwarded into production CC LXC with zero active REST/MCP jobs. Locked
dependencies synchronized; API/MCP restarted active and the CapSolver GUI stayed
active. Unauthenticated/authenticated API capabilities returned401/200, and an
authenticated MCP session listed35tools. The pinned peer review found no concrete
blocker; private memory-history review remained LIMITED because the connector
returned UNAUTHORIZED, while public memory/source evidence was checked.

After that recovery, one authorized local-reference count-one Auto CLI BDD passed:
one pass, one skipped MCP example, three deselected, two warnings in55.37seconds.
The image decoded and requested/resolved/policy aspect metadata matched. No
CapSolver task was required for this test. The first test-selection filter matched
no tests and consumed no allowance; the corrected selection consumed image slot2.
Slots1and2 are used; slot3 remains. This proves the CLI local-reference Auto path,
not native UUID/canonical grounding or registered MCP/REST generation acceptance.
Exact older-grid discovery and comprehensive feature parity remain unfinished.

## Bounded native grid discovery

The frozen exact-ID grid draft was integrated into the development worktree after
its eight regressions failed against the old implementation. Thirteen focused
discovery/real-DOM tests then passed in5.29seconds; the existing composer suite
passed135tests in28.38seconds. A separate read-only live probe located the original
reference among24mounted images and measured the unique scrollable page container.

The tagged no-submit grid BDD passed once with two deprecation warnings in9.95seconds.
It selected a fresh typed image with one active owned workflow outside the mounted
set, discovered its exact token, restored the original scroll position and removed
temporary per-document state. No upload, generation or solver was requested.
The first scenario selected from a broader snapshot and failed discovery; fixture
selection now excludes inactive/ambiguous workflows and unresolved dimensions.
One subsequent harness attempt omitted the required project_media project argument
and failed before discovery; it was corrected before the successful run.

The component passed pinned peer review and was published/deployed atbd6f71c5. Discovery/restoration proof does not establish accepted canonical grounding,
all-gallery completeness or generation through every public adapter.

The final boundary suite passed17tests in7.72seconds, and the combined existing
reference/discovery suite passed35tests in9.84seconds. The first full sweep found
eight obsolete scalar-grid test doubles; these now model the measured action/token
protocol, while retaining picker collision, reload, missing-tile and character-chip
checks. Missing-reference diagnostics retain the requested media ID.
The corrected full sweep passed5874tests with5skips and15warnings in184.48seconds
at88.95%coverage. Whole-tree Ruff/format and strict Pyright were clean.

Deployment fast-forwarded the clean production checkout after both REST and MCP
queues reported zero active jobs. Locked dependencies synchronized; both services
are active. REST capabilities returned401without authentication and200with
authentication on the configured LAN listener; MCP initialization listed35tools.
An initial verification probe used loopback for the LAN-only REST listener and
failed to connect; the configured listener check passed without a service change.

## Repeated native image captions

The fresh ownership helper incorrectly required a caption to be globally unique
among active workflows. Captions are labels; exact owned media/workflow IDs,
grid tokens and guarded outgoing IDs identify references. Only that caption-count
refusal was removed; ownership, type, budget and caption safety checks remain.

The hydration regression and combined SDK-to-picker positive/negative regressions
failed first on the old caption guard. The focused matrix then passed64tests.
CLI/MCP parity passed61tests. The tagged live no-submit scenario passed once
with one deselected scenario and two deprecation warnings in31.33seconds. It
hydrated a repeated-caption owned image, selected its exact token and observed one
media chip before clearing the composer; no generation request was observed.
The initial harness attempt deadlocked its single-page pool by holding a page
while SDK validation requested a lease, then timed out in121.56seconds. Returning
the discovery lease before validation fixed the harness; no production lease code
changed. Attachment proof does not establish canonical wire or accepted output.

The first full offline sweep passed5873tests with7skips but failed the packaging
test because the invocation's PATH did not contain uv. The corrected invocation
passed5876tests with5skips and15warnings in186.53seconds, with88.94%coverage.
Whole-tree Ruff/format and strict Pyright passed. Repository/doc/site/privacy and
public-memory checks passed; the duplication proxy reported only unchanged
experimental transport blocks. Sourcefd22da6a passed pinned peer review, was published to all three fork
references and deployed to the clean CC LXC checkout after both queues reported
zero active jobs. Locked dependencies synchronized; both services are active.
REST capabilities returned401/200for unauthenticated/authenticated requests, and
authenticated MCP initialization listed35tools. The CapSolver GUI stayed active.

## R02 ordered input and upload acknowledgement development draft

The explicit ordered-input helper now assigns local logical aliases at their
original numeric positions, preserving interleaved native/local/native slots.
CLI preflight/execution use it, and MCP includes the same plan/aliases in direct
and queued task payloads. The new helper regressions failed before implementation.
The helper/codec/slot matrix passed53tests in1.25seconds. The public MCP/CLI
ordering, payload and existing Auto matrix passed52tests in1.62seconds.

The measured maseQ flat response [media_id, project_id, ...] is decoded by its
fields, requiring exactly one upload frame, two UUID fields, the selected project
and a distinct media ID. Nested, foreign, reversed, malformed and duplicate-frame
responses refuse. Nine new decoder regressions failed before implementation.
The first expanded suite found12legacy fixtures whose requested project was the
placeholder p1 while the acknowledgement named a different UUID. Upload cases
now request the same real synthetic project UUID as their acknowledgement.
The corrected composer/image/prompt/mention/decoder suite passed194tests in29.01seconds.
Whole-tree Ruff/format and strict Pyright passed.

These are uncommitted development changes, not deployed behavior or accepted live
generation. Dispatch/file correlation and retained acknowledgements after partial
failure remain required, followed by REST native references/Auto, public docs,
tagged live verification and complete gates before publication/deployment.

## R02 REST native routing and correlated uploads — development draft

REST accepts an unregistered native image UUID only with an explicit configured
account. It queues ordered server-owned native/managed source records; the runtime
revalidates their exact shape, source identity, account ownership, MIME and managed
path containment. Native IDs are never registered as synthetic local assets.
The private worker retains separate native IDs, local aliases and managed paths.
Native-first Auto resolves fresh dimensions inside the selected-account worker
before upload/generation; managed-first Auto still decodes the actual first file.

The full selfhost matrix passed463tests in14.64seconds before the additional
boundary regressions. The selected REST suite subsequently passed12tests, then
14tests in0.96seconds including omitted-aspect default Auto and full-worker
dimension failure with generation never called. The affected composer/decoder/
prompt/selfhost/codec/CLI suite passed641tests in45.02seconds. Whole-tree Ruff
and strict Pyright passed at that draft revision.

A regression with a distinct stale media ID failed on the prior uncorrelated
response listener. Upload replies now require the exact observed request after
chooser dispatch; multiple observed upload requests are refused as ambiguous.
A partial batch failure regression failed first, then confirmed earlier
acknowledged IDs are returned through non-retryable native mutation recovery.
Canonical prompt binding failures retain newly uploaded IDs before generation.
A cancellation regression also failed first; cancellation keeps its original
exception and carries the same private recovery metadata as native video upload.
Generation submission remains outside the upload-preparation exception wrapper,
preserving typed Google generation refusal/unknown outcomes.

No R02 changes are committed, published or deployed yet. These offline proofs do
not establish live correlated uploads, exact current picker binding or accepted
mixed/native REST generation. Those remain separate live/gate requirements.

### Live upload contract correction

The first tagged no-generation upload scenario failed in18.29seconds: HTTP200
returned a shape the flat decoder refused. A fresh selected-project inspection
found exactly one active synthetic image workflow; its explicit archive was
acknowledged. This was an uploaded asset, not a generated image.

A second bounded schema-capture scenario failed in19.74seconds at the same
decoder and recovered/archived its exact unique-caption typed image in cleanup.
The response was retained privately with mode600. Matching its fields against
fresh typed project metadata established the current two-row response: the media
row names media/project/workflow; the workflow row repeats workflow/project and
names the same media with the requested upload caption. The image arm carries
JPEG MIME and48×32 dimensions. The nested shape, rather than a guessed recursive
UUID location, now has explicit positive and mismatched-identity/type regressions.
Ten new regressions failed first. The captured reply decodes to the fresh typed
image identity after correction. No generation, CAPTCHA solve or billed output
was requested by these probes; no paid image-generation allowance was consumed.
The corrected live binding proof and full gates remain pending at this entry.

The corrected tagged no-generation scenario passed once with two warnings
in39.95seconds. It uploaded one synthetic PNG, decoded the current correlated
acknowledgement, verified its unique fresh typed active identity and requested
caption, attached its canonical prompt slot, checked one media chip and archived
only that fixture. The generation route guard observed zero generation requests.
The corrected decoder/composer/native-prompt suite passed169tests in28.95seconds
and strict Pyright passed. This establishes current upload/attachment handling,
not accepted output or completed R02 fresh URLs. Full publication gates remain.

The first complete offline sweep passed5924tests with5skips but found7migrated
i2v BDD failures: their requested project was the placeholder p1 while their
shared upload reply named the synthetic project UUID. The same project-correlation
guard already passed the live image upload and focused composer checks. These
BDD inputs now use the reply's project UUID consistently, keeping start/end-frame
binding, confirm/picker and no-submit negatives intact. Coverage was88.29%;
publication remains gated on the corrected complete sweep.

The corrected complete sweep passed5932tests with5skips and15warnings
in180.05seconds at89.00%coverage; repo/doc/site/public-memory checks,
CLI/MCP61-test parity, Ruff/format and strict Pyright passed.
Pinned prepublication review approved account/security and CLI/MCP/order scope,
but found one upload cleanup recovery gap: removing a listener could throw after
a decoded acknowledgement before the caller appended its binding. Two new
regressions failed first. The upload driver now retains that current handle and
attempts both removals; a later upload recovery merges current and earlier
acknowledgements. Cancellation retains its original exception and recovery
metadata, while an existing primary error is preserved when no handle exists.
The targeted upload/decoder matrix passed33tests in1.20seconds and Pyright passed.
Publication waits for the corrected final gate and scoped re-review.

The final complete sweep after cleanup recovery passed5934tests with5skips
and15warnings in206.68seconds at89.00%coverage. Whole-tree lint/format,
strict Pyright, repository/doc/site/mirror/public-memory checks and61CLI/MCP
parity tests passed. The duplication proxy found only the unchanged experimental
bearer/SAPISID blocks. Pinned peer reviews approved ordering/public mirrors,
account security and the corrected upload/recovery boundary; the prior cleanup
CAUTION was cleared on staged treea27cfdf2. The27-file staged privacy scan found
zero configured solver-key or private account/project/media identifier matches.
Publication/deployment revision and runtime verification follow separately.

## R02 reference-routing publication and deployment

Feature source44c423660e34e7529ccf7114474533a5aee473ca was atomically published
to develop, feature/self-hosted-flow-api and feature/useapi-parity-2026-10-03.
The clean CC LXC production checkout fast-forwarded after REST created/running
and MCP pending/processing counts were bothzero, checked again with services
stopped. Locked dependencies synchronized and both services are active.

Deployed LAN REST capabilities returned401without authentication and200with
authentication. Authenticated MCP initialization listed35tools including image
generation. The CapSolver GUI returned200. The initial queue check used state
for the MCP table; source inspection confirmed its column is status and both
corrected counts passed before stopping services. The initial MCP probe assumed
an older three-stream return; the installed client returns two, and the corrected
initialization/tool-list check passed. No service change was needed for either
verification-harness correction.

The published/deployed batch implements ordered native/managed image references
and native-first Auto routing; its live proof is upload/canonical attachment/
archive with zero generation requests. Accepted native/mixed REST or registered
MCP images remain R12 requirements. R02 remains open for typed native asset lookup,
fresh protected URLs/downloads and verified useapi composite-ID translation.
The completed local implementation plan was consolidated into this ledger,
PARITY.md, API.md and the cited migrated-wire memory. No additional paid image
generation or CAPTCHA solve was performed.

##2026-10-03 — R02 fresh native image/video retrieval batch

Goal-turn classification: progress. The preceding roadmap-only verification did
not implement a new feature; this run revalidated clean9e859f2e source/deployment
and took the next available R02 action. The full R01–R13 objective remains active.

Implemented current existing-GetMedia identity/type decoding, separate from the
historical generation decoder. A fresh selected-project snapshot and strict one
as29s frame must match media/project/workflow and exclusive image/video plus
generated/uploaded unions. One bounded page checkout avoids concurrency-one
deadlock. Native UUID lookup never synthesizes local Store ownership.

Protected URL/download fields are measured from current public source and owned
live uploaded image/video metadata. SDK get_native_asset/download_native_asset,
CLI project get-media/download-media, direct MCP gflow_get_native_asset/
gflow_download_native_asset, and REST GETassets source=google now mirror this
read capability. URLs are explicit confidential synchronous output/no-store,
excluded from durable generation queues; useAPI GET is synchronous. REST native
raw=true/1 is video-only and invalid supplied raw controls return400.
Local managed metadata/download defaults remain separate.

Downloads use trusted exact HTTPS media URLs, no redirects/browser cookies,
bounded time/bytes, decoded type/dimensions, positive available metadata size and
exclusive output publication. Limits32MiB image/256MiB video. HTTPX's bearer URL
INFO logging is filtered per task, with an INFO-enabled privacy regression.
Temporary REST output cleanup wraps the ASGI response in finally, including
Range400/416, send failure and cancellation. Expected output errors are typed;
invalid/empty private worker replies are masked502.

Evidence:
- Red decoder/download scaffolds failed on absent modules before implementation;
  native REST scaffold failed6cases plus1auth pass before adapter wiring.
- Focused final codec/SDK/CLI/MCP/REST/cleanup tests:64passed in2.61s.
- Read-only initial content probe: JPEG1024x1024,233225bytes; MP4 H.2641280x1280,
  8908bytes. Both uploaded variants, with no guarded write requested.
- Tagged zero-write BDD: initial1pass/2warnings15.57s; final1pass/2warnings18.92s,
  concurrency one, decoded image/video content, exact identities and dimensions.
  No generation, upload, archive, restore, deletion, solver or paid allowance used.
- Complete offline sweep:6000passed,5skipped,212deselected,15warnings573.97s,
  89%reported coverage. Repo/doc/site/mirror/public-memory/Ruff/format/Pyright green.
- D0 staged hygiene:1512tracked files; docs229files all links resolving.
- SDK/MCP registry source inspection:37registered tools, including both new reads.
- Staged privacy scan38files:0configured private-key/account/project/media hits.

Council: source/tree8aaef7464638d8682d6b9dc91b83613812bf650a received GO for
security/transport/public-memory and source correctness/lifecycle/mirror scope.
Documentation CAUTION findings (tool count, limits, scope, final timing) were
corrected; doc-only treecd038921cd29212b6010e4816ffa57c2ca1d05fb received GO.
Private connector memory was unavailable and was not audited. Public source
and memory carry the reviewed identity, URL, logging and cleanup lessons.

Publication/deployment follow after this checked batch. R02 remains open for
voice/character-reference/thumbnail detail, composite translation and exact error
equivalence. Generated-arm URLs have source/codec proof, not live acceptance.
R12 final representative generation campaign remains pending.

### R02 retrieval publication and deployment

Feature revision b3d2523761443178e5503643bff1357970c6f86b was published atomically
to develop, feature/self-hosted-flow-api and feature/useapi-parity-2026-10-03.
All three GitHub refs were then verified. Production fast-forwarded to that
revision; REST/MCP queues were0before and after service stop. Locked dependency
sync completed and both services restarted active.

Actual deployed checks passed:
- REST authentication401/200, native image URL200 and Cache-Control:no-store.
- Registered HTTP MCP37tools, both new names present, native image lookup accepted.
- REST native raw MP4 returned8908verified bytes and removed temporary output.
- Registered MCP native image download returned233225verified local bytes with
  no URL in the download result; only the unique probe directory was removed.
- Initial MCP proof harness used old isError/structuredContent model attributes;
  installed client uses snake-case fields. The harness was corrected, with no
  product-code change or generation replay.

This verifies deployed read/download seams, not generation/full useAPI parity.
Next R02 work: character imageReferences preview URLs and avatar thumbnail URL,
plus typed user-voice playback detail. Current useAPI character detail documentation
also distinguishes system presets, attached live user voices and deleted/orphan
voices. Fresh ownership/source evidence must establish each form; absent partial
snapshots must not imply a deleted voice. Composite identity and exact error
equivalence remain explicitly unfinished.


## Character reference/thumbnail detail — 2026-10-03
The tagged character-detail-urls BDD passed once in39.12seconds (two pytest-BDD
deprecation warnings). One temporary character copied one existing owned image;
fresh project/entity/workflow-parent/primary-image correlation resolved its preview
and matching thumbnail URL. The test removed only its own character and verified
all original media remained present. Generation requests were guarded and zero.
This proves the projected reference-thumbnail form, not nonprojected variants,
saved-user-TTS playback, composite IDs or account-wide inventory.
SDK/CLI/MCP/REST detail is wired; publication/deployment remains pending.

Required offline gate:6014passed,5skipped,15warnings in182.32seconds using four
xdist workers and89%reported coverage. Ruff/format/Pyright and repository/docs/
website/public-memory checks passed. Council GO for pinned source tree; attached
saved-voice decoder remains an existing unfinished path. No source changes after
the full test run. Publication/deployment follows this checkpoint.
