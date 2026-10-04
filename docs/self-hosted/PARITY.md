# Google Flow / useapi parity inventory

Contract review: 2026-10-03. Baseline: upstream gflow-cli v0.82.1.
This is an implementation checklist, **not a claim of complete compatibility**.
A CLI command existing does not prove its migrated `flow.google.com` transport works.
Native Google upscaling is distinct from resizing with an image library.

## Evidence and status vocabulary

- **CLI**: a baseline command exists; adapter and live verification remain separate.
- **Migrated unported**: upstream explicitly rejects or has not ported this form; absence in gflow is not evidence that Google's UI cannot do it.
- **Missing**: no equivalent public CLI command found.
- **Local equivalent**: an implementation can reproduce the output locally, but does not perform the same Google-side operation.

Live baseline evidence available for text-to-image on the migrated host with two aspect ratios. Historical upstream baseline image upscale was rejected before submission; the fork supersedes that baseline with live-verified native2K CLI/HTTP/MCP results recorded below and in VERIFICATION.md. All3 registered account profiles have historical read-only health/catalog evidence; latest renewal failures are recorded in VERIFICATION.md. Accepted image generation is recorded separately; accepted native video rendering remains unverified in this deployment. Update this inventory alongside implemented adapter capabilities and verification evidence.

## Current fork endpoint inventory

All paths below use the useapi `/v1/google-flow` prefix; all calls require bearer authentication. Links are authoritative contract references. The final column describes the current fork, including transport limits and live proof boundaries. The historical upstream baseline lacked several migrated operations; it is preserved in the earlier investigation ledger rather than treated as the current feature status.

| Endpoint | Request contract / result | Current fork scope and evidence |
|---|---|---|
| [POST accounts](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts) | Cookie-table import; account configuration and refresh information | Private cookie-table import and staged identity/project access checks are implemented; rejected clone proof exists, successful live import remains pending. Credential values are deliberately not echoed. |
| [GET accounts](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts) | Object keyed by account email with health/configuration | Implemented registered-account listing with redacted operator-attested or native-cookie-verified metadata. On-demand native health is a separate queued extension, not automatic login refresh. |
| [GET accounts/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-email) | Account details for path email | Implemented selected registered-account metadata through explicit public handle/account mapping; no cookies or credentials returned. |
| [DELETE accounts/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-accounts-email) | Remove registered account | Implemented registration removal only; refuses active jobs and preserves browser profile files. |
| [POST accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts-captcha-providers) | Provider keys; empty key removes provider; masked response | Implemented private mode 600 key storage/removal and masked response for CapSolver/2Captcha. Actual CapSolver solve succeeded but its one Google submission was rejected; explicit image/native provider controls are implemented; accepted solver-backed output remains unverified. |
| [GET accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-providers) | Masked configured provider metadata | Implemented masked configuration metadata; configuration is not proof of accepted solver-backed generation. Loopback CapSolver key/balance GUI is a separate extension. |
| [GET accounts/captcha-stats](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-stats) | Solver usage / acceptance statistics | Implemented private counters separating solved/submitted/accepted/rejected/unknown outcomes. Actual trials recorded solved/submitted tokens with explicit Google refusals; matched local solve/acknowledgment timing is available without inferring orphan durations. |
| [POST assets/email](https://useapi.net/docs/api-google-flow-v1/post-google-flow-assets-email) | Raw content with MIME header; image or MP4 upload; account pinned | Implemented raw PNG/JPEG managed references and native MP4 ingestion; REST cap 20 MiB, portable SDK/CLI/MCP snapshot cap 250 MiB. MP4 exact true rights assertion is mandatory. Synthetic upload/archive lifecycle verified across SDK/CLI/registered MCP/HTTP; local-only image IDs are labeled. |
| [GET assets/mediaGenerationId](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-mediagenerationid) | Path opaque media reference; optional `raw`; metadata or bytes | Managed registry default plus source=google fresh owned image/video URLs and video-only raw. Native UUID lookup requires explicit configured account/project scope; image raw and invalid supplied native raw controls return400. SDK/CLI/direct MCP mirrors and zero-write image/video download BDD passed. Explicit scoped HTTP image/video alias registration/read/removal is implemented; opaque URL-safe prefixes are not decoded. Explicit character/saved-voice detail mappings are implemented separately; Exact registered supported HTTP generation/operation alias inputs are implemented; arbitrary vendor decoding, full thumbnail cohorts and exact404 equivalence remain open. |
| [GET assets/projects/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-projects-email) | Account projects; optional cursor pagination | HTTP defaults to bounded generated history; explicit source=local selects the managed catalog and source=google selects native opaque-cursor project snapshots. Two disjoint pages live verified; no inferred global completeness. SDK/CLI/MCP native mirrors also verified. |
| [GET assets/media/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-media-email) | Project media; optional `projectId` | HTTP defaults to source=google selected-project native timeline snapshots, including typed image/video arms; source=local selects the managed catalog. SDK/CLI/MCP mirrors verified; unknown completeness is explicit and absent rows do not imply deletion. |
| [DELETE assets/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email) | Required `mediaGenerationIds`1–100 image/video IDs; optional `projectId`; validate the whole batch first | Native reversible full-batch archive remains the default and is live verified. operation=delete now wires permanent selected-media deletion across SDK/CLI/MCP/REST, with source-derived preflight/acknowledgement checks; owned synthetic upload/delete lifecycle passed in 28.91 seconds after bounded metadata-only polling, preserving all original active media. localOnly cache deletion remains separate. Omitted projectId uses the selected account's configured project. Receipt-backed already-gone retries and mixed present/gone batches are verified; arbitrary absent UUIDs and all batch shapes are not claimed. |
| [POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) | See image parameter matrix | Implemented text/local-reference generation, seeds and explicit canonical image slots with weighted fresh native character ownership. One positional SDK image was accepted; CLI/MCP/HTTP positional acceptance remains pending after safe picker refusals. Configured provider controls and typed WAF-only explicit retries are implemented; acceptance and picker limits remain separate. |
| [POST images/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images-upscale) | `mediaGenerationId`, `resolution` default2k; captcha controls; encoded JPEG | Native 2K CLI/HTTP/MCP upscale live verified. 4K dispatch is implemented but Pro entitlement refuses it; accepted 4K requires appropriate entitlement and remains unverified. 2K/4K supplied/provider overrides and explicit1–10 positively confirmed WAF-only retries are implemented;4K checks current enabled availability before paid mint. |
| [POST videos](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) | See video parameter matrix | Text/start-end adapters and dedicated native image/audio R2V and Omni V2V adapters are wired across SDK/CLI/MCP/REST, with model discovery, typed ownership and output checkpoints. Video is disabled by default; paid acceptance is pending. Source-derived R2V character/positional grounding is wired; rendered acceptance/numerical seeds remain gaps. Generic count1-4 supplied/provider controls and dedicated native providers are implemented, including one-request all-output tracking; accepted rendering remains unverified. |
| [POST videos/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-upscale) | `mediaGenerationId`; resolution720p/1080p/4K default1080p; async/callback/captcha | HTTP defaults to native1080p promotion; explicit operation=export retains legacy export. Native720p/1080p/4k promotion has SDK/CLI/directMCP/privateworker surfaces, fresh tier/model checks and output dimension verification. Paid accepted promotion and4K entitlement proof remain R12; source construction is not output acceptance. |
| [POST videos/gif](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-gif) | `mediaGenerationId`; synchronous `encodedGif` | Implemented CLI 270p/native GIF export and HTTP encodedGif adapter. GIF export is not a paid live video proof; promotion/source-video acceptance remains unverified. |
| [POST videos/extend](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-extend) | `mediaGenerationId`, `prompt`, `model`, count 1–4, seed, async/callback/captcha | Standalone native extension is wired across SDK/CLI/MCP/REST with native model discovery, source ownership, independent output IDs and polling/download. Accepted paid extension output remains unverified; legacy scene-combining extension is separate. |
| [POST videos/concatenate](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-concatenate) | `media`2–10 items: ID, trimStart/trimEnd0–10s; sum trims less than clip duration; encodedVideo | Implemented local ffmpeg composition of 2–10 managed or freshly owned native clips with duration/trim/aspect checks, local artifact IDs and offline real-ffmpeg tests. This is labeled local composition, not Google-side scene editing; no paid generation required. |
| [POST voices](https://useapi.net/docs/api-google-flow-v1/post-google-flow-voices) | email, preset voice, dialog1–120 chars, voicePerformance1–120, displayName1–200, captcha | Native saved-TTS creation is wired across SDK/CLI/MCP/REST: one TTS preview then two metadata saves, with partial identities preserved. The first preview returned an ambiguous outcome without recovery handles; preset casing was corrected and the corrected captured request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), so rendered TTS acceptance is unverified. This is preset/dialog/performance generation, not voice cloning. |
| [GET voices](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices) | email required, source system/user optional | REST email-selected default combines fresh system and selected-project user voices; explicit bundled discovery remains. Dynamic native system preset catalog exists in SDK/CLI/MCP; same30 names live verified. Project-scoped source=user saved-TTS inventory is wired across SDK/CLI/MCP/REST; account-wide completeness and final live adapter proof remain pending. |
| [GET voices/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices-ref) | Preset name or custom ref; fresh audio URL for user voice | Implemented selected system preset lookup/sample metadata. Saved user-TTS detail uses strict typed ownership, fresh canonical base-preset/dialogue/performance metadata and optional playback URL across SDK/CLI/MCP/REST; REST no-store; published/deployed at3d35e1d5. Final live playback proof remains pending. |
| [DELETE voices/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-voices-ref) | Custom voice reference | Permanent selected saved-TTS deletion is wired across SDK/CLI/MCP/REST; final live lifecycle proof remains pending. System presets are not deletable. |
| [POST characters](https://useapi.net/docs/api-google-flow-v1/post-google-flow-characters) | displayName1–200, imageReference_1 required, optional second, personalityNotes≤2000, optional voice | Implemented project-scoped one/two-existing-image copy creation with notes and system preset metadata; owned saved-TTS voice binding is also wired with fresh ownership validation, pending final E2E; SDK/CLI/registered MCP/deployed HTTP lifecycle verified. Originals preserved. Legacy CLI create separately generates portraits; account-wide exact useapi semantics remain gaps. |
| [GET characters](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters) | email required | Implemented project-scoped native summaries in REST and shared SDK/CLI/MCP; live lifecycle/catalog reads verified. Not an account-wide inventory guarantee. |
| [GET characters/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters-ref) | Character ref; images/voice/thumbnail signed URLs | Native notes/preset metadata plus fresh ordered image previews and proven reference-thumbnail URLs are implemented across SDK/CLI/MCP/REST; projected-image detail BDD passed39.12seconds. Saved-user-voice acceptance, nonprojected thumbnail variants and composite refs remain open. |
| [DELETE characters/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-characters-ref) | Character ref | Implemented native permanent owned-character removal in REST/SDK/CLI/MCP, with explicit MCP confirmation and live cleanup proof. Unknown/partial acknowledgements preserve identity without replay. |
| [GET jobs](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs) | options=summary/executing/history; per-account load statistics, recent outcomes and executing/history detail | Explicit options=summary/executing/history now provides enabled verified account statistics, running metadata and newest10 terminal records per generation family from one SQLite snapshot. Default is summary; source=local selects the paginated job list. Timing includes queue waiting; admission429 and non-generation kinds remain distinct; exact native quota reasons now drive explicitly local automatic-selection cooldowns. SDK/CLI/MCP queued runner is separate. |
| [GET jobs/jobid](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs-jobid) | Job identifier; status, request/response/error | Implemented durable stable job ID with safe request/response/error projection, started/completed/failed states and callbacks. Unknown billed mutation outcomes retain safe handles and nonretryable inspection guidance. |

## Feature-batch checkpoint

The [published Flow index](https://useapi.net/docs/api-google-flow-v1) has **29
endpoint contracts**. All29 names are accounted for:20 have existing scoped
implementations and9 have source-derived paths now wired but key final acceptance
proof pending (account import, video generation/upscale/GIF/standalone extension,
and the four saved-user-TTS contracts). This is not a completion percentage or
exact compatibility claim. Earlier scoped implementations can also lack vendor
options or require representative live proof. Publication/deployment checkpoints
and live acceptance are recorded separately in the verification ledger.

| Newly wired capability | Current boundary |
|---|---|
| Derived Auto image aspect | CLI I2I and direct/queued MCP resolve the first local reference or fresh owned native image UUID dimensions. Local run-config/REST managed references retain their decoded-byte policy. Requested/resolved/policy retained; text/character-only and unavailable native dimensions refuse. No Google AUTO enum; unregistered REST native UUID lookup remains separate. |
| Saved TTS CRUD | SDK/CLI/MCP/REST create/list/detail/delete; project-scoped visible owned audio, unknown completeness. One preview followed by metadata saves; not voice cloning. Corrected captured TTS request Google-rejected (gRPC 7); no audio or binding lifecycle accepted. |
| Saved-voice character binding | Fresh owned saved audio can be assigned through character create/update; metadata semantics separate from rendered speech. Final binding E2E pending. |
| Permanent individual media removal | Explicit operation=delete removes selected owned media rather than archiving siblings. Default whole-batch archive remains reversible. Complete owned synthetic upload/delete lifecycle passed with bounded metadata polling, preserving all original active media. Already-gone semantics remain different. |
| Standalone extension | SDK/CLI/MCP/REST identify and download independent extension outputs; available native model keys/costs discovered. Legacy scene-concatenating command remains separate. Paid acceptance pending. |
| Omni V2V | SDK/CLI/MCP/REST edit one owned source clip, explicit native model key, optional end frame, inherited aspect, at most5 existing images/3 active owned native audio media IDs/7 character entities, further constrained by native combined capacities; canonical positional markers and mixed character/image slots are preserved. Omitted end uses measured source length at virtual24fps, rounded down/capped240; unavailable duration refuses before submission. Paid acceptance pending. |
| Native R2V image/audio | SDK/CLI/MCP/REST use source-derived reference DTO, fresh model/tier/reference limits, native images and owned saved-audio UUIDs. Native model discovery passed live reads. One browser-token generation attempt returned PUBLIC_ERROR_UNUSUAL_ACTIVITY; no rendered output accepted. |
| Native credit inspection | Shared SDK/CLI/MCP returns source-defined total balance/paygate/service tier, unknown subscription/SKU null. Shared service adapters require explicit native host mode; native read-only E2E passed. |

Native model discovery is available for extension, edit and reference-video modes; all three passed actual read-only E2E. The registered MCP surface exposes42 tools.
The same checked-out project page mints generation tokens. Preassigned identities
are derived from invocation-owned seeds, checkpointed before dispatch and
correlated with acknowledgements; ambiguous writes are not automatically replayed.
Focused source/codec tests establish implementation, not Google acceptance.

## Remaining concrete feature gaps

- Numerical video generation seeds and distinct4:3/3:4: current primary generation
  builders do not expose the seed and collapse those aspect enums. See the bounded
  [seed inspection](../superpowers/spikes/2026-10-04-generic-video-numeric-seed.md)
  and earlier aspect codec inspection.
- Accepted solver-backed output remains unverified. Generic count1-4 provider
  controls, all-output tracking, native2K/4K token overrides and explicit bounded
  WAF-only retries are implemented; traffic/unknown outcomes do not retry.
- Accepted rendered video/character/audio grounding, saved-TTS lifecycle and
  promotion remain R12 proofs; source construction/preflight is implemented.
- Native4K output on an entitled account. Three Pro subscriptions do not grant
  Ultra; image2K output is live verified and4K dispatch has fresh entitlement gates.
- Arbitrary vendor composite decoding and unobserved thumbnail/voice variants;
  exact registered typed aliases work, unsupported opaque refs remain explicit.
- Account-wide authoritative completeness/history/character/user-voice cohorts.
  Resumable URL-free synchronization is implemented across SDK/CLI/MCP/REST;
  traversal exhaustion remains distinct from complete=None and never deletes.
- Arbitrary already-gone raw UUID success cannot be inferred. Exact confirmed
  receipts and supported registered-alias mutations are implemented.
- Ten-reference rendering remains a final test. Exact ordered UI/wire retention
  passed a live abort-only test; Lite10 admission, separate character caps and
  actual image weights are implemented.
- Successful live cookie import/automatic renewal remains unproved. Accepted
  refresh lineage preserves aliases/jobs/stats/idempotency/receipts; saved-profile
  health is an observation rather than a guaranteed login lifetime.
- Exact vendor envelopes/error/timing/global-statistics semantics remain
  differences documented in CONTRACT_AUDIT.md. Exact native quota/model mapping
  and local cooldown routing are implemented; Google reset times remain unobserved.

Unknown controls fail explicitly before generation. Local ffmpeg concatenate is
not a Google scene join. Local registration/cache removal is distinct from native
resource deletion. The fork has its own bare UUID/managed references; existing
useapi composite refs cannot be reused without a verified mapping. Job IDs,
protected callbacks and unknown outcomes preserve safe recovery identities and
never expose tokens, cookies or solver keys.

## Roadmap

**R10 remains a priority; independent roadmap work continues.** The corrected
owned-login completion gate and fresh API health checks passed for both isolated
test profiles on 4 October. Automatic renewal is still missing; current health
does not prove an unattended login lifetime. Continue feature acceptance on those
two profiles while preserving the first account exclusively for UseAPI.
See [session health](SESSION_HEALTH.md#login-persistence-priority--4-october-2026).


This is the execution roadmap for the self-hosted fork and the source for a
persistent Goal-mode run. Work from the first unfinished item that can make
progress. A blocker on one item does not stop work on the others.

**Working order:** deliver features first, keep required correctness/privacy
checks, then run a representative final E2E campaign. Keep changes limited to
gflow-cli; Tee Pipeline and cloud-environment setup are outside this goal.
The deployment target is CC LXC. Three Google AI Pro subscriptions are available,
and all3 configured profiles have historical authentication/read-only health and
catalog verification. The first account is disabled in gflow and retained in
UseAPI; the two test profiles passed fresh post-deployment health checks.
Successful import/automatic renewal and rendered three-account acceptance remain
separate unverified requirements. CapSolver is the
chosen provider; configured keys and solved tokens do not prove Google acceptance.

### Completed foundations

- [x] Native image2K upscaling through CLI, REST and MCP, with accepted live output.
- [x] Auto sizing from local references and owned native image UUID dimensions on
  SDK/CLI/MCP. Native UUID sizing passed a read-only live test; accepted Auto
  generation passed through the local-reference CLI; native UUID and registered
  MCP/REST acceptance remain part of R01/R12.
- [x] Automatic video-edit end from measured source duration, with explicit
  overrides and SDK/CLI/MCP/REST wiring. Read-only duration verification passed;
  edited-video rendering remains part of R12.
- [x] CapSolver private configuration, masked key GUI, balance checks and outcome
  statistics. Solver-backed accepted generation remains part of R06.

### Overnight implementation status

The table records concrete delivered code, not a blanket completion claim.
Focused tests and independent reviews accompany each batch; R12 owns accepted
rendering and R13 records the published revision.

|Task|Implementation ready for final E2E|Open implementation or external boundary|
|---|---|---|
|R01|Current composer, cookie banner, positive-index controls and explicit append caret; live exact ordered ten-reference wire capture passed|Rendered ten-reference output remains R12|
|R02|Fresh typed media/character/saved-voice URLs and exact alias inputs|Unobserved variants/arbitrary vendor encoding|
|R03|Resumable SDK/CLI/MCP/REST sync plus bounded account characters/saved voices with opaque continuation|Global authoritative completeness unknown|
|R04|Canonical image/entity/audio reference transport and fresh capacities|Rendered grounding remains R12|
|R05|Bounded current-codec investigation complete|Numeric generation seed/five distinct ratios lack a working contract|
|R06|Image/native/generic count1–4 providers;2K/4K overrides; positive WAF-only retries and one-use supplied tokens|Accepted solver output remains R12|
|R07|Native720p/1080p/4K promotion, default1080p; image2K/4K entitlement guards|Accepted promotion/entitled4K remains R12/access dependent|
|R08|Lite10, independent character/image pools and fresh weighted caps; live ten-chip/wire proof passed|Rendered proof remains R12|
|R09|Exact alias mutation and scoped confirmed-delete receipts|Unproven arbitrary missing IDs cannot become success|
|R10|Atomic accepted-refresh lineage, historical three-account health, fresh-principal checks and staged Session-cookie retention|Successful import/automatic renewal proof; both isolated test profiles currently pass fresh health|
|R11|All29contract audit, defaults, WebP, local event timing, native concat/inputsCount, exact quota mapper/cooldowns and generic all-output batches|Vendor opaque IDs/envelopes and inferred reset semantics remain explicit differences|

### Ordered feature backlog

The IDs are stable so a Goal-mode run can record its current item. Check a feature
item only when its implementation, applicable SDK/CLI/direct and queued MCP/REST
surfaces, documentation and relevant tests are complete. Record live acceptance
separately under R12; an existing command or passing mock is insufficient evidence.

- [x] **R01 — Current Flow image composer and asset picker.** Finish and integrate
  the current-cohort composer/grid work so local references, native UUIDs, Auto
  sizing and canonical image/character references reach the correct owned assets.
  Use fresh structural/source evidence; resolve ambiguity before submission.
  Current evidence: expanded chat removed the mode chip before the old recovery
  checked it. A bounded close-then-reprobe fix passed the live zero-submit BDD
  (one pass, two warnings,15.21seconds); classic settings became visible. The
  recovery is published/deployed at64974ba0. A count-one local-reference Auto CLI
  BDD passed (one pass, one skip, three deselected, two warnings,55.37seconds),
  with a decoded image and expected aspect metadata. The bounded grid draft now
  passes17offline boundary tests plus a live active-image discovery/restoration BDD
  (one pass, two warnings,9.95seconds), and is published/deployed atbd6f71c5. Native
  UUID/canonical-reference and registered MCP/REST accepted
  output remain pending. The SDK global caption-uniqueness restriction is removed
  in published/deployed sourcefd22da6a; a tagged live repeated-caption hydration/
  attachment BDD passed (one pass, one deselected, two warnings,31.33seconds)
  without generation. Unsafe captions now use a bounded contiguous safe excerpt and require a unique
  exact owned thumbnail token. Canonical uploaded references use that same token
  path when their caption cannot be typed safely. The live unsafe-caption upload/
  canonical-attachment/archive BDD passed in37.41seconds with zero generation
  requests. Empty captions preserve fresh owned UUIDs and use a bare picker,
  but actual empty-caption live coverage is pending. Accepted output still needs
  its own R12 proof.
- [ ] **R02 — Native media lookup and fresh URLs.** Remaining work is owned
  image/video/voice/character-reference/thumbnail lookup beyond the local registry,
  remaining typed detail/thumbnail variants and verified composite translation. Image/video UUID URL/download adapters are already published/deployed, with
  selected-account/project ownership and no Store synthesis. Later exact alias
  inputs and scoped general-video caching are recorded below. Correlate account,
  project, media and type; keep local/native scope explicit. Translate useapi
  composite IDs only with a verified mapping.
  Native/mixed image generation routing is published/deployed at44c42366: unregistered native
  UUIDs require an explicit configured REST account; server-owned ordered source
  records preserve managed paths and original slots through the private worker.
  CLI/direct and queued MCP share the same ordered plan/local alias contract.
  Native-first Auto resolves fresh dimensions in the selected-account worker;
  managed-first Auto decodes the actual first local file. Missing dimensions
  never fall back to another reference.
  Current toolbar upload acknowledgements are request-correlated typed nested
  media/workflow rows, matching project/media/workflow, unique requested caption,
  MIME and dimensions. Earlier/current upload handles survive later upload,
  binding, cancellation and listener-cleanup failures without automatic replay.
  The tagged upload/owned-identity/canonical-binding/archive BDD passed once
  in39.95seconds with zero generation requests; the final complete offline suite
  passed5934tests with5skips at89.00%coverage. These establish implementation and
  attachment, not accepted mixed/native REST or registered MCP output; R12 retains
  those acceptance requirements. Image/video lookup/download now has current public-source field evidence, strict current GetMedia identities/unions, trusted content validation and synchronous SDK/CLI/MCP/REST mirrors. The zero-write uploaded image/video BDD passed with concurrency one in18.92seconds. At the b3d25237 image/video checkpoint, generated-arm/detail/composite/error evidence was still open; later generated-image and character-detail/alias evidence is recorded below. Exact error equivalence and live saved-user audio remain open. Registered HTTP MCP37tools, REST native URL/raw video and MCP lookup/image download passed actual deployed read checks. Character reference/thumbnail detail was implemented and subsequently published with ordered workflow-parent/primary-image joins and SDK/CLI/MCP/REST wiring. The tagged live detail BDD passed in39.12seconds with fixture cleanup and zero generation. This character-image batch is published/deployed at1216368e; actual deployed REST no-store and registered MCP include_urls reference/thumbnail reads passed with fixture removal; Candidate primary images omitted from the media projection and independently
projected thumbnails now have strict owned workflow/GetMedia adapters; unresolved
workflow variants and composite semantics remain open. Saved-user voice fresh
performance/dialogue/preset/playback details are published at3d35e1d; live saved
user playback coverage remains R12. R01 caption implementation is published and
deployed atf802e754 with6037offline tests passing and the37.41s no-generation
unsafe-caption canonical attachment proof.
  Follow-up 2026-10-04: exclusive generic audio metadata now requires an active
  owned workflow and strict GetMedia, with null dimensions and metadata-only
  playback; the downloader remains image/video-only and HTTP assets refuse audio400.
  Explicit character thumbnail candidates omitted from the media projection now
  resolve through exact GetMedia plus fresh active character-parent ownership.
  Fresh generated-image lookup/download/inventory membership passed on pro1
  (one new1024×1024 image). The existing zero-generation asset/character/catalog
  BDD batch passed3tests in72.25seconds. Explicit HTTP image/video alias bindings now require fresh ownership and exact
  media/type checks; alias removal affects local mappings only. Opaque prefixes
  do not decode vendor identity. Their original read-only input boundary was
  superseded by the exact registered HTTP input batch documented below. Broader
  composite translation, exact error equivalence and live saved-user audio
  acceptance remain open.
- [ ] **R03 — Complete inventories and synchronization.** Page and reconcile
  account-wide projects, attached media/history and character/user-voice
  inventories. Expose completeness and counts only when established; a partial
  snapshot or absent row must not imply deletion.
  Bounded native account project traversal is now implemented across SDK,
  CLI `--all-pages/--max-pages`, direct MCP and REST `allPages/maxPages`.
  Counts are unique returned identities; page caps preserve continuation.
  Exhaustion is reported separately from `complete=None`; cycles/duplicates
  refuse and no absent row triggers deletion. The live two-page read-only
  BDD passed in9.04seconds, then repeated in13.86seconds with concurrency
  explicitly pinned to one and zero generation. At that traversal checkpoint attached media/history and account-wide character/
  user-voice inventories remained open; later attached-media and bounded-history
  deliveries are recorded below. Complete character/user-voice cohorts remain gaps.
  Optional include_catalogs/max_projects now aggregates observed media, workflow
  history, characters and saved user voices from one fresh payload per project.
  CLI/MCP and REST includeCatalogs/maxProjects share the one-page/180second
  boundary, known counts and explicit pending discovered IDs. The one-project
  live BDD passed10.14seconds with zero generation. At that catalog checkpoint account-history paging was not implemented. It is now
  published at41784983 with bounded continuation and durable REST observations.
  Generated-only per-call summaries are now implemented and passed actual default
  HTTP/read proof. Complete history and authoritative/destructive reconciliation
  remain unproven; unknown completeness never becomes deletion evidence.
  Follow-up 2026-10-04: read inventories now merge the source-derived timeline
  and attached collection, preserve origin/attachment project identities, exclude
  positively verified bundled preset wrappers, and expose exact typed upload
  classification plus validated source timestamps. Strict ownership parsers retain
  their separate same-project default. HTTP native media lists all observed rows
  by default; explicit pagination is a fork extension. count/likelyUploads describe
  returned rows and observedCount the full snapshot. Cached real payloads passed
  for all3 accounts (53/556/565 observed media), and fresh catalog BDD passed in the
 3-test batch. Later41784983 delivers bounded generation-history paging and metadata-only
  observation upserts. Complete history and authoritative reconciliation remain
  open; no absent row authorizes deletion.
  Fresh isolated-profile follow-up: SDK, CLI, deployed registered MCP and REST
  each passed a new discovery/catalog read and a real subsequent catalog resume
  for both character and saved-user-voice kinds. Each also passed fresh inventory
  sync plus catalog-committing resume. No zero-page or cached continuation was
  counted as fresh access. The documented account-resources CLI alias is now
  registered alongside resources; both spellings share one implementation.
  Sampled resource counts were zero in two bounded catalogs, not evidence of
  absence or globally complete cohorts; complete remains null and deletion
  authority false.
- [ ] **R04 — Video reference and character coverage.** Implement canonical
  positional image/entity/audio grounding and video character references. Extend
  V2V beyond existing image/saved-TTS UUIDs to supported uploaded audio, system
  presets and character inputs. Discover actual source contracts before enabling
  each form; an attachment alone does not prove semantic grounding.
  Generic native-audio edit preflight is now implemented without saved-TTS
  visibility, with exact active workflow and exclusive audio proof. Read-only
  preflight BDD passed7.68seconds; uploaded-audio/rendered acceptance remains R12.
  R2V character inputs and preserved mixed canonical slots are now wired across
  SDK/CLI/registered MCP/REST/privateworker with native combined budgets. Free
  fixture BDD passed42.07seconds with0generation. V2V character/positional
  transport now shares fresh classification, actual reference weights and model
  limits across SDK/CLI/direct MCP/REST/privateworker. The free synthetic video/
  character preflight BDD passed55.13seconds before token mint, with0generation,
  fixture cleanup and originals preserved. Direct system presets now normalize
  known names/exact native resources, require fresh unique native catalog proof
  and consume actual audio pools across R2V/V2V and all existing interfaces.
  Free system-preset R2V/V2V preflight BDD passed45.63seconds at both token
  boundaries, with0generation, synthetic cleanup and originals preserved.
  Rendered grounding remains open for R12.
  Follow-up 2026-10-04: one canonical owned-character R2V attempt on pro2 selected
  the cheapest fresh compatible model (4seconds,360p,4credits). Google explicitly
  rejected the single submission with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC7):
  accepted outputs0, no retry. It counts as1of2 video attempts in the new campaign.
  A read-only alternative-engine probe exposed missing main-world WIZ context;
  a private correction passed native model reads with0generation. The production page-context correction was subsequently published/deployed
  at4f2b4cc3, with an actual pro3 read-only model BDD. The later pro3
  character+preset submission was explicitly WAF-rejected, accepted0,unknown=false.
  Accepted rendered character/audio/video proof remains open.
- [x] **R05 — Native video controls (bounded discovery, limits recorded).** Find and wire numerical video seeds and
  distinct 4:3/3:4 video ratios if the service exposes them. The currently observed
  codec collapses those ratios: do not ship extra input choices that produce the
  wrong shape. Record a source-backed limitation if investigation cannot
  establish a working contract, and continue other items.
  Current build poKdDH1IwKU.2018.O independently confirms the ratio collapse.
  Its source-derived generation builder has no numerical seed in text/reference/
  frames/edit/extension branches; metadata assignment UUID seeds are distinct.
  Numerical seed is observed only on UPSAMPLE_VIDEO field4, tracked in R07.
  Unsupported native generation controls remain explicit refusals. This closes
  bounded R05 discovery, not useapi seed/five-ratio output equivalence; see the
  linked primary codec inspection above.
- [ ] **R06 — CapSolver and CAPTCHA control coverage.** Complete supplied-token
  and CapSolver selection/control wiring for image/video/upscale/extension/TTS
  paths where applicable. Investigate the rejected replacement-token integration
  with matched action, browser/session context and controlled attempts. Separate
  solve, submission, explicit rejection and unknown outcomes; never replay an
  uncertain write. Keep unverified provider paths explicitly guarded until an
  accepted live result proves them. Prior trials solved tokens but Google
  rejected their submissions; acceptance is an unfinished proof requirement.
- [ ] **R07 — Real resolution promotion and entitlement handling.** Establish
  native 360p-to-720p promotion, video4K and accepted image4K where account
  entitlement permits. Downloads/exports/local resizing do not establish native
  promotion. Discover actual account capability and return clear limits; three
  Pro subscriptions do not establish Ultra access. Preserve the working image2K
  path while investigating higher resolutions.
- [ ] **R08 — Reference budgets and remaining image controls.** Cover the
  documented reference forms/counts with current per-model limits, including
  ten-image cases where actually supported. Lite10 admission and separate character budgets are implemented; actual ordered ten-chip/wire retention and one decoded owned image passed. Per-reference visual influence remains R12.
  Keep first-reference ordering and validation consistent across surfaces.
  Native Google Auto remains separate from the implemented approximation.
- [ ] **R09 — Individual-delete compatibility.** Establish exact already-gone
  semantics and complete supported batch behavior with fresh owned membership
  proof. Preserve permanent deletion versus reversible archive versus local-cache
  deletion as distinct operations; do not infer success from incomplete listings.
  Delivered: scoped confirmed-delete receipts, exact fresh NOT_FOUND, zero-write
  repeat requests and present-only mixed batches. Arbitrary already-gone raw
  UUIDs remain unprovable; see NATIVE_MEDIA.md. Free synthetic proof43.96seconds.
- [ ] **R10 — Account import, refresh and three-account coverage.** Prove a
  successful cookie-table import, supported session refresh/reuse and independent
  account selection/queues for all three Pro accounts. Preserve private profiles
  and identity verification; Google may still require human login. Prepare
  everything possible before requesting a required login, then continue other
  items while it is pending. Three distinct Pro profiles are registered and passed concurrent read-only health jobs (three started concurrently, zero generation requests). A cookie-table transfer was rejected; human-assisted sign-in restored the original second profile. Successful import/atomic refresh and rendered three-account coverage remain unverified.
- [ ] **R11 — Remaining useapi contract equivalence.** Audit all 29 endpoint
  contracts and parameter matrices against the finished adapters: defaults,
  supported controls, response/error fields, sync/async status, polling,
  callbacks and timeout/unknown semantics. Unknown controls must fail explicitly
  before generation. Update the endpoint matrix and API documentation with exact
  scope instead of declaring parity from endpoint-name coverage. R11 delivery: HTTP native asset deletion defaults to the selected account's registered project; explicit invalid values refuse. Deprecated image model aliases normalize to current Nano2/Lite models; landscape/portrait image aspects and explicit native promotion4K normalize to canonical controls. Explicit job statistics options now provide account-load views with honest timing/rate-limit scope; default summary and score-based automatic selection are implemented; reason/model quarantine is now implemented under the explicit local compatibility policy; Google reset times remain unobserved. The 29 primary contracts were retrieved for comparison; the full29endpoint audit is in CONTRACT_AUDIT.md with delivery changes and remaining differences.

### Final verification and delivery

- [ ] **R12 — Representative final E2E campaign.** Prepared matrix: [FINAL_E2E.md](FINAL_E2E.md). After the feature backlog,
  verify accepted text/local/native-reference images, canonical grounding, Auto,
  native2K, available higher-resolution paths, video generation/reference/edit/
  extension/export/GIF, saved TTS CRUD/binding and native media lifecycles.
  Exercise REST and registered MCP, including queued paths where different code
  runs, callbacks/recovery and available account entitlements. Use existing paid
  test authorizations and remaining allowances; do not start an unbounded stress
  test or repeatedly submit the same known refusal. Prefer read-only checks until
  an integration change justifies a new paid trial.
- [ ] **R13 — Publish, deploy and reconcile documentation.** Published baseline before the composer/upload delivery batch: 890a65918255d5a71065a82af0e0bd61a404c2b0,
  with REST/MCP/GUI active and both test accounts passing fresh queued health.
  Further roadmap batches remain in progress. Publish completed
  work to the GitHub fork, deploy it on CC LXC without interrupting active jobs,
  verify actual API/MCP capabilities, and update this roadmap, endpoint matrix,
  [API guide](API.md) and [verification ledger](VERIFICATION.md). Record code
  revision, tests, accepted outputs and precise remaining limitations.

### Goal-mode execution rules

1. Read this file and the verification ledger at the start of each resumed run.
   Inspect deployed/source state before choosing the next unfinished item.
2. Continue implementation and independent investigations autonomously within
   existing authorization. Do not end the run just because one feature, commit
   or test batch finished, or because another item is awaiting Google/login.
3. Keep a compact status for each active item: implementation progress, next
   concrete action, evidence and any blocker. Record unresolved investigation
   attempts with dates and outcomes; do not repeatedly run an unchanged failure.
   Update this roadmap after meaningful delivery, without inventing percentages.
4. Ask only for genuinely missing access, a necessary human login, an exhausted
   paid allowance or a scope decision. Complete preparatory work first and keep
   working on independent items while waiting.
5. Follow repository development/gate requirements without expanding this into
   an unrelated reliability rewrite. Publish and deploy concrete completed
   features as they become ready; perform the comprehensive E2E campaign last.
6. Keep implementation and live acceptance distinct. Do not check R12 or declare
   complete useapi parity from mock tests, solved CAPTCHA tokens, configured
   subscriptions or read-only metadata proofs.
7. Respect Goal-mode budget/status rules and explicit user pauses. A budget
   limit is not completion. If unresolved work remains, preserve the next task
   and evidence for resume; do not mark the goal complete merely by relabeling
   every remaining item as blocked. An unavoidable parity limitation requires
   a user scope decision before claiming the full goal is achieved.

### Copyable Goal-mode prompt

```text
Use docs/self-hosted/PARITY.md, especially its Roadmap section, as the source
of truth. Continue the Fograd/gflow-cli self-hosted fork toward full useapi
Google Flow parity on CC LXC.

Work through R01–R11 in order, selecting the next item that can make progress.
Deliver features first, mirror applicable SDK/CLI/direct and queued MCP/REST
surfaces, document them on GitHub, and publish/deploy completed changes.
Then run R12's representative final E2E campaign and finish R13.

Keep working within the goal budget instead of ending after one feature or
test batch. If one item is blocked, record actual evidence and continue other
independent work. Use existing authorizations and paid test allowances; ask
only when required access, login, additional paid allowance or a scope decision
is genuinely missing. Do not work on Tee Pipeline or cloud-environment setup.

Keep this roadmap and VERIFICATION.md current. Distinguish implemented code,
accepted live output and external limitations. Do not invent completion
percentages or claim complete parity while unresolved work remains.
```

## Existing proof and remaining final E2E

Earlier live evidence establishes native image2K, seeds, one/two-image character
metadata CRUD and preset assignment, notes clearing while preserving voice/images,
project paging (21+21 disjoint), mixed media reads, dynamic30 system presets,
and four synthetic MP4 upload/reversible-archive adapter lifecycles. Native credit
and extension/edit/reference model discovery passed actual read-only E2E. Permanent
individual owned synthetic lifecycle passed in 28.91 seconds after bounded metadata-only polling, preserving all original active media. Saved TTS/binding, Auto and paid video
acceptance remain independent final proof obligations. The first native R2V browser-token
attempt was explicitly rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY; a controlled
CapSolver native-video trial solved once and submitted once but was explicitly rejected (gRPC 7), with zero accepted output and no retry. See [verification](VERIFICATION.md).

Canonical image grounding has one accepted native SDK image with exact positional
wire checks. Three later CLI wrapper attempts refused before submission
(hydration, duplicate copied-caption ambiguity, then an owned asset absent from
the visible grid); all produced zero images and cleaned owned temporary entities.
HTTP/CLI/registered-MCP canonical image acceptance remains pending. Grid discovery
is a frozen draft and cannot be described as a deployed fix. These fork picker
limits do not prove Google lacks the capability.

Earlier empty-dialogue preset-picker probes did not persist metadata; subsequent
preset assignment proofs superseded them. Custom saved TTS is now separately
coded/wired. Its first preview had an ambiguous outcome without returned handles;
Charon casing was corrected; the captured corrected request was explicitly rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), with no accepted audio or binding lifecycle.
Rendered speech acceptance is not established. Earlier upstream
unported/501 observations are historical boundaries, not current feature-absence
claims. Full response/error field equivalence, representative timeout behavior,
paid output quality and per-profile entitlement remain independent proof obligations.

## Guide links

- [Auto aspect](../AUTO_ASPECT.md)
- [Saved TTS voices](VOICES.md)
- [Native MP4 and deletion](NATIVE_MEDIA.md)
- [Standalone extension](NATIVE_VIDEO_EXTENSION.md)
- [Omni editing](../VIDEO_EDIT.md)
- [Native reference video](NATIVE_REFERENCE_VIDEO.md)
- [Native credits](../NATIVE_CREDITS.md)
- [Job semantics](HTTP_JOB_SEMANTICS.md)

Captures stay private. Public findings describe operations, bounded DTO shapes and
verification results, without logged-in identities, private projects, raw requests
or tokens. Update this inventory together with capability/API documentation and
record final live proof separately.

## Completed controlled provider-video trial

The native VIDEO_GENERATION CapSolver Enterprise v3 proxyless trial solved one token and submitted one count-one R2V request. Google rejected it with PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC 7: accepted outputs zero, rejected requests one, no retry. The earlier provider-image trial is separate. Across the two private trial ledgers there were two solved tokens, two submitted requests, zero accepted outputs and two rejections. API counters remain scoped to each self-hosted instance. Provider acceptance is not proven. The feature batch is published and deployed; successful provider acceptance and full parity remain unproven.

## Final measured lifecycle update

Permanent individual deletion passed its owned synthetic upload→delete lifecycle: one passed and four skipped in 28.91 seconds; all original active media remained active. The corrected canonical Charon TTS preview captured one no0P6 request and was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7): one failed and four skipped in 17.93 seconds. No audio or saved-voice binding lifecycle was accepted. Extension and edit generation were not additionally billed after the same account's reference-video/TTS refusals; their live model catalogs remain the proof, with rendered acceptance unverified.

The final CLI local-Auto attempt failed at shared migrated composer readiness with exit 25 (FlowAgentUiError): one failed and four skipped in 54.38 seconds, no accepted image. MCP received no additional paid retry after this shared blocker. That generation failure is historical; the later read-only native UUID sizing BDD passed in7.68seconds against a1024×1024 owned image→1:1. Rendered Auto generation acceptance remains unverified; native Google Auto is unsupported.


### Native page context and fresh inventory follow-up — 2026-10-04

Page-owned WIZ/RPC evaluation now uses the existing engine-specific main-world
policy for Patchright, without globally changing evaluation or Playwright kwargs.
The pro3 affected-model-read BDD exited0 with zero generations. This establishes
page-context native model discovery, not accepted rendering or CAPTCHA solving.
Deployed6a264 native inventory subsequently returned pro1=51 and pro2=557 observed
rows, complete:null. These later fresh observations supplement the earlier cached
53/556/565 observations; neither establishes complete account history.
R02/R03/R04 remain unchecked until their broader evidence requirements are met.


### R03 measured account-history continuation — 2026-10-04

Bounded LWkPYd account-history reads now have SDK list_native_history and optional
existing project-list enrichment through CLI/MCP/HTTP include-history controls.
The prior private read-only observation returned20 workflows/20 media on the
default request and20 disjoint workflows/20 media using the returned continuation,
with a changed cursor and zero writes. The subsequent actual SDK BDD passed1test in18.39seconds: explicit [20,null]
initial request plus continuation yielded2pages/40joined workflows and media with
zero guarded writes. HTTP affected-surface BDD and full frozen-source gates remain
pending.

Traversal is capped at50 pages/1000 media/45seconds, returns URL-free native DTOs
and separates pagination_exhausted from complete:null. Project discovery/catalog
controls remain independent. Generated-only project summaries, complete account
history, saved-voice cohorts and reconciliation remain gaps; R03 stays unchecked.
Previous4f2b4cc3 detail/alias/page-context batch is published across all3 accounts
and deployed with services active; owned pro2/pro3 fixtures were cleaned while
original media remained preserved. This is not deployment evidence for the new
uncommitted history batch.

Pro2/pro3 separate live45-second bounded SDK reads returned300/220 workflows and
media respectively across15/11 pages, timed_out:true, pagination_exhausted:false,
complete:null and resumable cursors; each observed one project and no audio. These
are bounded observations, not complete account inventories. REST-only durable
inventoryObservations now upserts validated metadata under the exact configured
account/profile, excludes URLs/prompts/captions/cursors and preserves absent
observations without deleting or establishing fresh GetMedia authority. R03 stays open.


### R02 explicit resource aliases — 2026-10-04

HTTP character and saved-user-voice aliases now have explicit fresh-owned
registration/detail/local-removal routes. Character image count is exactly1or2
and excludes thumbnails; an optional voice suffix requires active saved-user
workflow/audio proof, not a system preset. Saved-voice aliases verify distinct
workflow/audio IDs and protected playback. Opaque URL-safe prefixes are not vendor
identity. The original detail-only batch did not widen inputs; the later exact
HTTP input batch is recorded below, while resource DELETE/CRUD mutation inputs
retain their existing raw contract. SDK/CLI/MCP remain raw.
Actual character alias REST BDD passed on pro1:1passed,1saved-voice fixture skip,
2warnings in26.26seconds, with zero generation/Google mutation. Fresh registration,
no-store read, local removal and raw original read were verified. Saved-user audio
requires a suitable fixture/user permission and remains pending. Final source
gates passed6602tests,5skips,89%coverage; R02 stays unchecked.

Prior history batch41784983 is published across all3 registrations and deployed
with services active. Its actual SDK18.39s and REST18.77s two-page/40joined-media
proofs remain separate from this new resource-alias batch and full history claims.


### R03 explicit catalog resume — 2026-10-04

Implemented ordered catalog_project_ids resume through SDK, repeat CLI
--catalog-project-id, direct MCP and REST catalogProjectIds.1–20unique UUIDs
require native catalog inclusion and exclude account cursor/traversal controls.
max_projects/maxProjects bounds reads and preserves pending order; no account
pages/names are synthesized. REST observed metadata now includes empty projects,
characters and saved source:user voices with transactional identity checks and
no protected URLs or absence-based deletion. Actual pro1 SDK resume BDD passed14.52seconds and REST resume/resource-cache
BDD passed18.81seconds, each1test with zero generation; REST made zero Google
mutation and proved positive character/idempotent counts. Explicit resume responses
require matching selected-project source paths. Owned fixture cleanup passed with original character IDs/source image preserved
and zero generations; final gates passed6649tests,5skips,89%coverage; complete cohorts/history and authoritative reconciliation remain open.

R02 resource-alias batch a7f293240f436069fa6efa21fdf8f253b24a7a7e is now published
to all3 fork branches and production, with synchronized environment and API/MCP
services active, queues0. This deployment record does not claim the new catalog
resume batch is deployed or saved-user voice acceptance is complete.


### R02 registered HTTP alias inputs — 2026-10-04

Implemented: exact registered image/video/character/saved-voice inputs resolve
before account selection/queueing with fresh scope/type/resource proof. Canonical
UUID slots and existing worker checks remain; no protected URL/signature/token
persists. General video privately caches verified PNG/JPEG image aliases up to
20MiB under exact account/project, with atomic store registration. Raw SDK/CLI/MCP,
preset strings and resource DELETE/character CRUD mutation inputs are unchanged.

Actual workers-disabled alias/cache/queue BDD passed1test in64.71seconds: owned
1024image registration/fresh read, validated cache bytes and canonical Omni4second
360p start-frame queueing. Zero generation; queue admission is not output proof.
Focused42HTTP/cache cases and councilGO passed; strict Pyright0errors.

The native count1pro1 mixed character/image/Charon trial preserved canonical
reference slots3/7 but Google explicitly refused unusual activity, accepted0.
CapSolver01 failed before solve/post,0jobs/generation, reservation released.
CapSolver02 solved1token but failed before browser/Google submission because its
root loader required intentionally stripped daemon credentials. The shared
path-only environment_root correction is implemented; private token checks stay
unchanged, with4red-to-green regressions and64focused passes in13.71seconds.
CapSolver02 statistics/ledger were corrected:0Google submits/generation and
reservation released, originals retained privately. CapSolver03 then solved1token
and submitted through the fixed worker; Google explicitly refused unusual activity,
accepted0. It proves solving/forwarding, not accepted provider-backed generation.
Pro1 video allowance is2of2 consumed; no further pro1 paid video trial is authorized.

Final frozen-source gates passed6746tests,5skips,15warnings,89%coverage in
322.79seconds. Repository/link/PII/mirror/council/Ruff/format checks and whole
source strict Pyright0errors passed. Published atomically to all3 fork branches and clean fast-forward deployed at
source ea9cc2c5bc8ee35362ee81427fb1b1c83bff9a6e; environment synchronized, API/MCP
active, queues0 before/after actual production reads. The earlier6693pass checkpoint preceded the root-loader correction; the final
6746pass result certifies the corrected source.
Rendered/provider acceptance, saved-user voice cohort and broader R02 remain open.

R03 catalog-resume671589efcf724c35206f8e58458380101e4aff60 is published across
all3 fork branches and production, environment synchronized, API/MCP active,queues0.
This preceding deployment does not include the current alias-input/default batch.

### R03 generated-history summaries and HTTP defaults — 2026-10-04

Implemented: positive generated image/video arms supply per-call project totals,
by-type counts and valid source date extrema. Uploaded/audio/unknown rows do not
contribute generated totals; scanned counts all verified observed media. HTTP
projects defaults to source=history; explicit google retains project discovery/
catalog resume and local retains managed cache. Media defaults to native google.
SDK/CLI/MCP history gains additive classifications/summaries without new flags/tools.
Traversal remains50pages/1000media/45seconds with atomic verified pages, retained
continuation and unknown consistency/completeness.

A measured later page had20workflows/19media and one declared primary absent.
The codec omits only that unverified link; present wrong-owner primaries refuse.
It retains20workflows/19media/scanned19 without inventing media. Final focused
88cases passed7.31seconds, strict Pyright0errors and RuffGO.

Actual default-summary/media BDD passed1test,2warnings in65.84seconds. It verified
current-project generated IMAGE totals/date bounds, scanned/truncated continuation,
private0600 scoped observations and the original blue-vase image in default native
media. Workers disabled:0durable jobs/generations. The owned pro1 character fixture
was cleaned through fresh reads, preserving source image/original character IDs,
with0generation.

Final frozen-source gates passed6746tests,5skips,15warnings,89%coverage in
322.79seconds. Repository/link/PII/mirror/council/Ruff/format checks and whole
source strict Pyright0errors passed. Published atomically to all3 fork branches and clean fast-forward deployed at
source ea9cc2c5bc8ee35362ee81427fb1b1c83bff9a6e; environment synchronized, API/MCP
active, queues0 before/after actual production reads. The earlier6744checkpoint overlapped the missing-primary correction; the final
6746pass result above certifies the frozen correction.
Production proof is recorded below. R03 remains unchecked for complete histories,
saved-user cohorts and authoritative reconciliation; no accepted R04 video is claimed.

Actual deployed default history HTTP200 passed for all3 accounts at source
ea9cc2c5:pro1 projects3/scanned138;pro2 projects1/scanned260;pro3 projects1/
scanned200. All were truncated:true, complete:null, with validated continuations
and generated totals no greater than scanned. Private result files were0600.
These are fresh bounded observations, not complete account inventories.

Zero generation; campaign reservations unchanged:pro1 images1/videos2,pro2
images0/videos1,pro3 images1/videos1. API/MCP remained active and queues0. No
accepted native video/provider-backed rendering is claimed. Docs-only follow-up
reuses the unchanged frozen source6746pass gate; no source rerun is needed.


## 4 October overnight feature checkpoint
Implementation delivery and accepted output remain distinct; release revisions and
final R12 tests must be recorded separately.
| Item | New delivery | Remaining evidence or limit |
|---|---|---|
|R02/R04| Real saved-TTS preview tests and playback/binding paths | Browser and CapSolver preview WAF-refused; accepted lifecycle pending |
|R03| Resumable project/catalog/history traversal; atomic URL-free checkpoint; SDK/CLI/MCP/REST | Real two-step resume passed; global completeness unknown |
|R06| Image/native/generic count1-4 providers and explicit1–10 WAF-only retry;2K/4K overrides with fresh availability | Actual solver-backed rendering pending |
|R08| Lite10, separate character cap, weighted image cap; corrected caret retains all ten exact ordered references | One decoded owned ten-reference output accepted; per-reference visual influence remains R12 |
|R09| Exact registered alias mutation inputs, strict confirmed-delete receipts | Arbitrary vendor decoding and unknown missing IDs unsupported |
|R10| Atomic accepted-refresh lineage, aliases/stats/idempotency/receipt continuity | Successful live import and automatic renewal unverified |
|R11| Full29endpoint audit, summary jobs, combined voices, exact quota mapper/local cooldowns, WebP, elapsed event filters, native concat/inputsCount/default1080p promotion | Several vendor envelopes/defaults remain differences |

Retained allowances and fresh ownership govern final E2E. Feature progress is not
a completion percentage.


### Next overnight source batch
Generic count1 provider SDK/CLI/queued MCP/REST controls,2K/4K provider refusal retries with entitlement-before-mint, and bounded account character/saved-voice continuation are implemented. See [generic providers](GENERIC_VIDEO_CAPTCHA.md) and [account resources](ACCOUNT_RESOURCES.md). Source tests/reviews and release revision must be recorded before calling this batch deployed.

The actual ten-reference attachment probe after the270second deadline correction still failed291.83seconds with zero captured/forwarded generation requests. A separate first-miss diagnostic found two attached references then zero options for the third26-character query. This is a current picker defect requiring R01 work, not a native capacity rejection or accepted R08 proof. Successful cookie import/automatic renewal and accepted external-token audio/video remain external acceptance boundaries.


### Ten-reference composer defect fixed and live checked
The failed third query was caused by the editor center-click moving the caret into existing prompt content. Existing-reference preattachment now explicitly appends at the end while preserving exact owned thumbnail-token matching. An isolated real-browser DOM regression went RED then GREEN for the third reference and ten ordered chips. The actual logged-in HARBOR_SEAL abort-only BDD then passed1test in226.35seconds: all ten native identities and canonical prompt order reached the intercepted request, Google dispatch0, own fixtures archived and original active media preserved. This closes the reproduced picker implementation defect; accepted ten-reference rendering remains R12.


The staged Session-retention fix now has real isolated Chrome coverage and an actual cookie-reader proof. The copied jar retains SAPISID and reaches GOOGLE_SESSION_ONLY; identity/project verification still rejects, with original profiles preserved. A new real2K CapSolver request was traffic-refused once with no output. See [verification](VERIFICATION.md) for exact release and budget boundaries.

### Third overnight implementation batch
Generic video count2–4 uses one request, actual all-output handles/downloads/checkpoints and explicit common-context provider controls across SDK/CLI/MCP/REST. The real count4Lite capture passed with four exact unique IDs and Google forwarding0. Exact typed quota/model refusals now propagate through workers/jobs and local automatic routing. JSON-equivalent bounded multipart text fields and matched-observer CAPTCHA elapsed statistics are implemented; deep/malformed requests refuse before queue. Retired profile re-registration is guarded. See [video batches](VIDEO_BATCH.md), [account scheduler](ACCOUNT_SCHEDULER.md) and [form contracts](FORM_REQUESTS.md).

Human boundary: pro2 fresh Flow entry now redirects to Google accountchooser; no renewal is possible while the operator sleeps. Pro1 remains usable and fresh official GetPeople returned one exact me record/status1/expected principal with0generation. This positive proof is being used to correct current-host identity verification; copied cookies still require independent fresh identity/project proof before activation. Native numeric seeds, unavailable account4K entitlements, unknown global catalog completeness and arbitrary vendor composite decoding are not invented as completed features.

### Final source freeze boundary
The third batch is source-frozen with independent form/OpenAPI, all-output/provider, quota and auth/retention reviews. Current headed standalone verifier and a repeated SDK GetPeople check failed onpro1 after earlier positive proofs; successful import remains blocked. Do not interpret the earlier positive principal/editor observations as current three-account authentication readiness. Pro2 reached Google sign-in explicitly; final R12 must renew/recheck sessions. No identity guards were relaxed.


### Published overnight handoff

Three overnight feature batches were published/deployed: `b8aba7b4`, `41363f94`,
and `1e68b30c`. The final frozen-source gate passed7,684tests,5skips and90%coverage,
with strict types/lint/format/docs/mirrors checked. Current API/MCP/GUI and
JSON/multipart contract proofs are in [verification](VERIFICATION.md).

Most scoped feature adapters are ready for their final representative tests;
R01-R11 are **not all complete** under the broad compatibility/acceptance criteria.
Successful cookie import/renewal, accepted solver-backed saved audio/video and
entitled4K are still unproved. Numeric video seed/distinct extra ratios,
arbitrary vendor encodings and authoritative global completeness retain the
recorded current-contract limits. These are explicit remaining boundaries;
passing source tests do not close them.

Latest pro1 and pro3 direct Google identity returned401; pro2 requires sign-in.
Earlier positive principal/editor proofs do not establish current access. Short valid resource
continuations with zero catalog reads are not renewed-session evidence. The final
[E2E run list](FINAL_E2E.md#executable-scenario-list) records executable scenarios,
prerequisites and the two remaining single-video allowances. No sleeping-user
login request or extra paid-video allowance was requested overnight.


### Composer and video upload corrections — 4 October

The ten-reference campaign exposed a second composer defect: Ctrl+A cleared only the focused chip (ten became nine). Whole-editor Range selection plus a normal Backspace editing event clears all ten; an intercepted browser regression went RED then GREEN. One subsequent single-output request retained all ten ordered native identities and yielded a freshly owned 768x1376 JPEG. The first harness looked for its requested PNG instead of the returned JPEG path. Read-only recovery verified the existing output and archived all ten owned fixtures, without generation replay. This proves accepted output from a ten-reference request, not independent visual influence of every reference.

The video rights failure was a Patchright negative-index counting defect: last-dialog counted zero buttons while positive index zero counted three. Positive dialog selection preserves the exact three-button check and chooses only the one-time agreement. Intercepted browser BDD went RED then GREEN; fresh isolated pro3 upload/delete BDD passed in50.83seconds: three synthetic uploads, two deletion writes, zero already-gone retry writes, present-only mixed deletion and originals preserved. Zero generation credits or solver calls.

Automatic session renewal, accepted solver-backed audio/video and entitlement dependent higher-resolution results remain unfinished proofs. Pro1 remains reserved for UseAPI. Cookie transfer testing remains suspended.


Corrected fresh ten-reference BDD follow-up passed: captured1, source dispatch-attempt1, ten exact ordered identities, accepted outputs1, decoded768x1376, fresh output ownership true, whole-composer clear10to0, owned fixture cleanup succeeded. This is a new authorized single image, separate from the earlier recovered output. No replay of the earlier invocation occurred.


### Composer/upload delivery gate — 4 October

Clean-shell whole gate passed7724tests,5skipped,21warnings in234.65seconds with89.60%coverage. Repository hygiene, documentation links, published PII/mirror/navigation, council memory, Ruff, format and strict Pyright all passed. Independent review GO89focused tests; final character-double/environment-focused100tests passed. Separate actual Patchright ten-reference rendering and isolated pro3 upload/delete retry proof passed. Source baseline890a6591; publication/deployment is the next checkpoint and subsequent capability work remains separate.
