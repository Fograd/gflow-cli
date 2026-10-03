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

Live baseline evidence available for text-to-image on the migrated host with two aspect ratios. Historical upstream baseline image upscale was rejected before submission; the fork supersedes that baseline with live-verified native2K CLI/HTTP/MCP results recorded below and in VERIFICATION.md. Video generation and other account profiles have not been live verified in this deployment. Update this inventory alongside implemented adapter capabilities and verification evidence.

## Current fork endpoint inventory

All paths below use the useapi `/v1/google-flow` prefix; all calls require bearer authentication. Links are authoritative contract references. The final column describes the current fork, including transport limits and live proof boundaries. The historical upstream baseline lacked several migrated operations; it is preserved in the earlier investigation ledger rather than treated as the current feature status.

| Endpoint | Request contract / result | Current fork scope and evidence |
|---|---|---|
| [POST accounts](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts) | Cookie-table import; account configuration and refresh information | Private cookie-table import and staged identity/project access checks are implemented; rejected clone proof exists, successful live import remains pending. Credential values are deliberately not echoed. |
| [GET accounts](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts) | Object keyed by account email with health/configuration | Implemented registered-account listing with redacted operator-attested or native-cookie-verified metadata. On-demand native health is a separate queued extension, not automatic login refresh. |
| [GET accounts/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-email) | Account details for path email | Implemented selected registered-account metadata through explicit public handle/account mapping; no cookies or credentials returned. |
| [DELETE accounts/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-accounts-email) | Remove registered account | Implemented registration removal only; refuses active jobs and preserves browser profile files. |
| [POST accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts-captcha-providers) | Provider keys; empty key removes provider; masked response | Implemented private mode 600 key storage/removal and masked response for CapSolver/2Captcha. Actual CapSolver solve succeeded but its one Google submission was rejected; provider generation controls remain HTTP 501. |
| [GET accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-providers) | Masked configured provider metadata | Implemented masked configuration metadata; configuration is not proof of accepted solver-backed generation. Loopback CapSolver key/balance GUI is a separate extension. |
| [GET accounts/captcha-stats](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-stats) | Solver usage / acceptance statistics | Implemented private counters separating solved/submitted/accepted/rejected/unknown outcomes. One paid CapSolver trial recorded 1 solved / 1 submitted / 0 accepted without retry. |
| [POST assets/email](https://useapi.net/docs/api-google-flow-v1/post-google-flow-assets-email) | Raw content with MIME header; image or MP4 upload; account pinned | Implemented raw PNG/JPEG managed references and native MP4 ingestion; REST cap 20 MiB, portable SDK/CLI/MCP snapshot cap 250 MiB. MP4 exact true rights assertion is mandatory. Synthetic upload/archive lifecycle verified across SDK/CLI/registered MCP/HTTP; local-only image IDs are labeled. |
| [GET assets/mediaGenerationId](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-mediagenerationid) | Path opaque media reference; optional `raw`; metadata or bytes | Managed registry default plus source=google fresh owned image/video URLs and video-only raw. Native UUID lookup requires explicit configured account/project scope; image raw and invalid supplied native raw controls return400. SDK/CLI/direct MCP mirrors and zero-write image/video download BDD passed. Composite handles, character/voice/thumbnail detail and exact404 equivalence remain open. |
| [GET assets/projects/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-projects-email) | Account projects; optional cursor pagination | Implemented local catalog default and source=google native 21-item opaque-cursor snapshots. Two disjoint pages live verified; no inferred global completeness. SDK/CLI/MCP native mirrors also verified. |
| [GET assets/media/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-media-email) | Project media; optional `projectId` | Implemented managed local catalog default and source=google selected-project native timeline snapshots, including typed image/video arms. SDK/CLI/MCP mirrors verified; unknown completeness is explicit and absent rows do not imply deletion. |
| [DELETE assets/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email) | Required `mediaGenerationIds`1–100 image/video IDs; optional `projectId`; validate the whole batch first | Native reversible full-batch archive remains the default and is live verified. operation=delete now wires permanent selected-media deletion across SDK/CLI/MCP/REST, with source-derived preflight/acknowledgement checks; owned synthetic upload/delete lifecycle passed in 28.91 seconds after bounded metadata-only polling, preserving all original active media. localOnly cache deletion remains separate. Already-gone idempotence and all batch shapes are not claimed. |
| [POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) | See image parameter matrix | Implemented text/local-reference generation, seeds and explicit canonical image slots with weighted fresh native character ownership. One positional SDK image was accepted; CLI/MCP/HTTP positional acceptance remains pending after safe picker refusals. Provider controls remain HTTP 501; see image matrix and picker limits. |
| [POST images/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images-upscale) | `mediaGenerationId`, `resolution` default2k; captcha controls; encoded JPEG | Native 2K CLI/HTTP/MCP upscale live verified. 4K dispatch is implemented but Pro entitlement refuses it; accepted 4K requires appropriate entitlement and remains unverified. CAPTCHA overrides are not complete upscale parity. |
| [POST videos](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) | See video parameter matrix | Text/start-end adapters and dedicated native image/audio R2V and Omni V2V adapters are wired across SDK/CLI/MCP/REST, with model discovery, typed ownership and output checkpoints. Video is disabled by default; paid acceptance is pending. Source-derived R2V character/positional grounding is wired; rendered acceptance, direct preset audio, numerical seeds and CAPTCHA overrides remain gaps. |
| [POST videos/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-upscale) | `mediaGenerationId`; resolution720p/1080p/4K default1080p; async/callback/captcha | Current fork has CLI `video upscale` and HTTP `/videos/upscale` adapters for native 1080p export and original 720p download. These are exports, not verified resolution promotion; 4K is unported and paid live video export proof remains pending. |
| [POST videos/gif](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-gif) | `mediaGenerationId`; synchronous `encodedGif` | Implemented CLI 270p/native GIF export and HTTP encodedGif adapter. GIF export is not a paid live video proof; promotion/source-video acceptance remains unverified. |
| [POST videos/extend](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-extend) | `mediaGenerationId`, `prompt`, `model`, count 1–4, seed, async/callback/captcha | Standalone native extension is wired across SDK/CLI/MCP/REST with native model discovery, source ownership, independent output IDs and polling/download. Accepted paid extension output remains unverified; legacy scene-combining extension is separate. |
| [POST videos/concatenate](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-concatenate) | `media`2–10 items: ID, trimStart/trimEnd0–10s; sum trims less than clip duration; encodedVideo | Implemented local ffmpeg composition of 2–10 managed owned clips with duration/trim/aspect checks, local artifact IDs and offline real-ffmpeg tests. This is labeled local composition, not Google-side scene editing; no paid generation required. |
| [POST voices](https://useapi.net/docs/api-google-flow-v1/post-google-flow-voices) | email, preset voice, dialog1–120 chars, voicePerformance1–120, displayName1–200, captcha | Native saved-TTS creation is wired across SDK/CLI/MCP/REST: one TTS preview then two metadata saves, with partial identities preserved. The first preview returned an ambiguous outcome without recovery handles; preset casing was corrected and the corrected captured request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), so rendered TTS acceptance is unverified. This is preset/dialog/performance generation, not voice cloning. |
| [GET voices](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices) | email required, source system/user optional | Implemented bundled offline default and dynamic native system preset catalog in REST/SDK/CLI/MCP; same 30 names live verified. Project-scoped source=user saved-TTS inventory is wired across SDK/CLI/MCP/REST; account-wide completeness and final live adapter proof remain pending. |
| [GET voices/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices-ref) | Preset name or custom ref; fresh audio URL for user voice | Implemented selected system preset lookup/sample metadata. Saved user-TTS detail uses strict typed ownership, fresh canonical base-preset/dialogue/performance metadata and optional playback URL across SDK/CLI/MCP/REST; REST no-store; published/deployed at3d35e1d5. Final live playback proof remains pending. |
| [DELETE voices/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-voices-ref) | Custom voice reference | Permanent selected saved-TTS deletion is wired across SDK/CLI/MCP/REST; final live lifecycle proof remains pending. System presets are not deletable. |
| [POST characters](https://useapi.net/docs/api-google-flow-v1/post-google-flow-characters) | displayName1–200, imageReference_1 required, optional second, personalityNotes≤2000, optional voice | Implemented project-scoped one/two-existing-image copy creation with notes and system preset metadata; owned saved-TTS voice binding is also wired with fresh ownership validation, pending final E2E; SDK/CLI/registered MCP/deployed HTTP lifecycle verified. Originals preserved. Legacy CLI create separately generates portraits; account-wide exact useapi semantics remain gaps. |
| [GET characters](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters) | email required | Implemented project-scoped native summaries in REST and shared SDK/CLI/MCP; live lifecycle/catalog reads verified. Not an account-wide inventory guarantee. |
| [GET characters/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters-ref) | Character ref; images/voice/thumbnail signed URLs | Native notes/preset metadata plus fresh ordered image previews and proven reference-thumbnail URLs are implemented across SDK/CLI/MCP/REST; projected-image detail BDD passed39.12seconds. Saved-user-voice acceptance, nonprojected thumbnail variants and composite refs remain open. |
| [DELETE characters/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-characters-ref) | Character ref | Implemented native permanent owned-character removal in REST/SDK/CLI/MCP, with explicit MCP confirmation and live cleanup proof. Unknown/partial acknowledgements preserve identity without replay. |
| [GET jobs](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs) | options, executing, completed, failed, rateLimited filters | Implemented durable REST SQLite jobs, bounded filters/cursor and canonical public status projection. SDK/CLI/MCP queued runner is a separate surface; exact useapi rate-limited filter equivalence is not claimed. |
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

Native model discovery is available for extension, edit and reference-video modes; all three passed actual read-only E2E. The registered MCP surface exposes37 tools.
The same checked-out project page mints generation tokens. Preassigned identities
are derived from invocation-owned seeds, checkpointed before dispatch and
correlated with acknowledgements; ambiguous writes are not automatically replayed.
Focused source/codec tests establish implementation, not Google acceptance.

## Remaining concrete feature gaps

- Numerical video seeds and complete video/upscale/TTS supplied-token/provider
  CAPTCHA controls. Provider keys/statistics are implemented; one solved CapSolver
  trial was Google-rejected and provider-backed image generation remains guarded501.
- Five distinct Veo aspect ratios: current native video codec collapses4:3/3:4;
  input-choice expansion alone would misstate support. See the
  [primary codec inspection](../superpowers/spikes/2026-10-03-veo-five-aspect-codec.md).
- Accepted rendered video character/entity grounding. R2V/V2V character and
  canonical positional image/entity/audio transport is implemented; attachments
  and free preflight do not establish rendered semantic acceptance.
- Native360p-to-720p promotion and video4K; three Pro subscriptions do not establish
  Ultra entitlements. Image2K is live verified; accepted image4K remains unverified.
- Arbitrary remote media and complete fresh signed image/character/voice/thumbnail
  resolution beyond currently supported managed/saved-TTS paths.
- Account-wide merged attached-media/history counts, account-wide character/voice
  inventories and full native library synchronization. Snapshot absence is not deletion.
- Exact already-gone individual-delete compatibility; registry/operator scope and
  native deletion acknowledgement remain distinct from useapi opaque IDs.
- Full ten-image model budgets: the measured Lite cap stays3; arbitrary
  direct system-preset inputs on the dedicated V2V form. Native audio and
  character inputs are implemented; rendered acceptance remains pending.
  Image Auto supports owned native UUID dimensions on CLI/MCP; unregistered native
  UUID lookup on REST and native Google Auto remain separate gaps.
- Successful live cookie-table import and automatic refresh are not established.
  Existing saved-profile reuse/project-access health proof is an observation, not
  a login-lifetime guarantee.

Unknown controls fail explicitly before generation. Local ffmpeg concatenate is
not a Google scene join. Local registration/cache removal is distinct from native
resource deletion. The fork has its own bare UUID/managed references; existing
useapi composite refs cannot be reused without a verified mapping. Job IDs,
protected callbacks and unknown outcomes preserve safe recovery identities and
never expose tokens, cookies or solver keys.

## Roadmap

This is the execution roadmap for the self-hosted fork and the source for a
persistent Goal-mode run. Work from the first unfinished item that can make
progress. A blocker on one item does not stop work on the others.

**Working order:** deliver features first, keep required correctness/privacy
checks, then run a representative final E2E campaign. Keep changes limited to
gflow-cli; Tee Pipeline and cloud-environment setup are outside this goal.
The deployment target is CC LXC. Three Google AI Pro subscriptions are available,
but only the configured first account has been verified so far. CapSolver is the
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
  remaining typed detail/thumbnail variants and verified composite translation. Image/video UUID URL/download adapters are implemented in the current batch with selected-account/project ownership and no Store synthesis. Correlate account,
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
  those acceptance requirements. Image/video lookup/download now has current public-source field evidence, strict current GetMedia identities/unions, trusted content validation and synchronous SDK/CLI/MCP/REST mirrors. The zero-write uploaded image/video BDD passed with concurrency one in18.92seconds. Generated-arm live coverage, voice/character/thumbnail detail, useAPI composite mapping and exact error equivalence remain open; this image/video batch is published/deployed atb3d25237. Registered HTTP MCP37tools, REST native URL/raw video and MCP lookup/image download passed actual deployed read checks. Character reference/thumbnail detail is now implemented in the working tree with ordered workflow-parent/primary-image joins and SDK/CLI/MCP/REST wiring. The tagged live detail BDD passed in39.12seconds with fixture cleanup and zero generation. This character-image batch is published/deployed at1216368e; actual deployed REST no-store and registered MCP include_urls reference/thumbnail reads passed with fixture removal; Candidate primary images omitted from the media projection and independently
projected thumbnails now have strict owned workflow/GetMedia adapters; unresolved
workflow variants and composite semantics remain open. Saved-user voice fresh
performance/dialogue/preset/playback details are published at3d35e1d; live saved
user playback coverage remains R12. R01 caption implementation is published and
deployed atf802e754 with6037offline tests passing and the37.41s no-generation
unsafe-caption canonical attachment proof.
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
  explicitly pinned to one and zero generation. Attached media/history and
  account-wide character/user-voice inventories remain open until catalog delivery.
  Optional include_catalogs/max_projects now aggregates observed media, workflow
  history, characters and saved user voices from one fresh payload per project.
  CLI/MCP and REST includeCatalogs/maxProjects share the one-page/180second
  boundary, known counts and explicit pending discovered IDs. The one-project
  live BDD passed10.14seconds with zero generation. Complete history/paging
  beyond the measured project snapshot and destructive synchronization remain
  unimplemented; unknown completeness never becomes deletion evidence.
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
  fixture cleanup and originals preserved. Direct system presets and
  rendered grounding remain open.
- [ ] **R05 — Native video controls.** Find and wire numerical video seeds and
  distinct 4:3/3:4 video ratios if the service exposes them. The currently observed
  codec collapses those ratios: do not ship extra input choices that produce the
  wrong shape. Record a source-backed limitation if investigation cannot
  establish a working contract, and continue other items.
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
  ten-image cases where actually supported. The measured Lite cap remains 3.
  Keep first-reference ordering and validation consistent across surfaces.
  Native Google Auto remains separate from the implemented approximation.
- [ ] **R09 — Individual-delete compatibility.** Establish exact already-gone
  semantics and complete supported batch behavior with fresh owned membership
  proof. Preserve permanent deletion versus reversible archive versus local-cache
  deletion as distinct operations; do not infer success from incomplete listings.
- [ ] **R10 — Account import, refresh and three-account coverage.** Prove a
  successful cookie-table import, supported session refresh/reuse and independent
  account selection/queues for all three Pro accounts. Preserve private profiles
  and identity verification; Google may still require human login. Prepare
  everything possible before requesting a required login, then continue other
  items while it is pending.
- [ ] **R11 — Remaining useapi contract equivalence.** Audit all 29 endpoint
  contracts and parameter matrices against the finished adapters: defaults,
  supported controls, response/error fields, sync/async status, polling,
  callbacks and timeout/unknown semantics. Unknown controls must fail explicitly
  before generation. Update the endpoint matrix and API documentation with exact
  scope instead of declaring parity from endpoint-name coverage.

### Final verification and delivery

- [ ] **R12 — Representative final E2E campaign.** After the feature backlog,
  verify accepted text/local/native-reference images, canonical grounding, Auto,
  native2K, available higher-resolution paths, video generation/reference/edit/
  extension/export/GIF, saved TTS CRUD/binding and native media lifecycles.
  Exercise REST and registered MCP, including queued paths where different code
  runs, callbacks/recovery and available account entitlements. Use existing paid
  test authorizations and remaining allowances; do not start an unbounded stress
  test or repeatedly submit the same known refusal. Prefer read-only checks until
  an integration change justifies a new paid trial.
- [ ] **R13 — Publish, deploy and reconcile documentation.** Publish completed
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
