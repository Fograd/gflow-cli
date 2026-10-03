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
| [GET assets/mediaGenerationId](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-mediagenerationid) | Path opaque media reference; optional `raw`; metadata or bytes | Implemented managed registry metadata/download and raw bytes. Arbitrary remote IDs are not a complete remote lookup; unknown upload handles are inspection-only and not registered as successful assets. |
| [GET assets/projects/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-projects-email) | Account projects; optional cursor pagination | Implemented local catalog default and source=google native 21-item opaque-cursor snapshots. Two disjoint pages live verified; no inferred global completeness. SDK/CLI/MCP native mirrors also verified. |
| [GET assets/media/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-media-email) | Project media; optional `projectId` | Implemented managed local catalog default and source=google selected-project native timeline snapshots, including typed image/video arms. SDK/CLI/MCP mirrors verified; unknown completeness is explicit and absent rows do not imply deletion. |
| [DELETE assets/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email) | Required `mediaGenerationIds`1–100 image/video IDs; optional `projectId`; validate the whole batch first | Native reversible full-batch archive remains the default and is live verified. operation=delete now wires permanent selected-media deletion across SDK/CLI/MCP/REST, with source-derived preflight/acknowledgement checks; owned synthetic upload/delete lifecycle passed in 28.91 seconds after bounded metadata-only polling, preserving all original active media. localOnly cache deletion remains separate. Already-gone idempotence and all batch shapes are not claimed. |
| [POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) | See image parameter matrix | Implemented text/local-reference generation, seeds and explicit canonical image slots with weighted fresh native character ownership. One positional SDK image was accepted; CLI/MCP/HTTP positional acceptance remains pending after safe picker refusals. Provider controls remain HTTP 501; see image matrix and picker limits. |
| [POST images/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images-upscale) | `mediaGenerationId`, `resolution` default2k; captcha controls; encoded JPEG | Native 2K CLI/HTTP/MCP upscale live verified. 4K dispatch is implemented but Pro entitlement refuses it; accepted 4K requires appropriate entitlement and remains unverified. CAPTCHA overrides are not complete upscale parity. |
| [POST videos](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) | See video parameter matrix | Text/start-end adapters and dedicated native image/audio R2V and Omni V2V adapters are wired across SDK/CLI/MCP/REST, with model discovery, typed ownership and output checkpoints. Video is disabled by default; paid acceptance is pending. Character/positional grounding, numerical seeds and CAPTCHA overrides remain gaps. |
| [POST videos/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-upscale) | `mediaGenerationId`; resolution720p/1080p/4K default1080p; async/callback/captcha | Current fork has CLI `video upscale` and HTTP `/videos/upscale` adapters for native 1080p export and original 720p download. These are exports, not verified resolution promotion; 4K is unported and paid live video export proof remains pending. |
| [POST videos/gif](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-gif) | `mediaGenerationId`; synchronous `encodedGif` | Implemented CLI 270p/native GIF export and HTTP encodedGif adapter. GIF export is not a paid live video proof; promotion/source-video acceptance remains unverified. |
| [POST videos/extend](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-extend) | `mediaGenerationId`, `prompt`, `model`, count 1–4, seed, async/callback/captcha | Standalone native extension is wired across SDK/CLI/MCP/REST with native model discovery, source ownership, independent output IDs and polling/download. Accepted paid extension output remains unverified; legacy scene-combining extension is separate. |
| [POST videos/concatenate](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-concatenate) | `media`2–10 items: ID, trimStart/trimEnd0–10s; sum trims less than clip duration; encodedVideo | Implemented local ffmpeg composition of 2–10 managed owned clips with duration/trim/aspect checks, local artifact IDs and offline real-ffmpeg tests. This is labeled local composition, not Google-side scene editing; no paid generation required. |
| [POST voices](https://useapi.net/docs/api-google-flow-v1/post-google-flow-voices) | email, preset voice, dialog1–120 chars, voicePerformance1–120, displayName1–200, captcha | Native saved-TTS creation is wired across SDK/CLI/MCP/REST: one TTS preview then two metadata saves, with partial identities preserved. The first preview returned an ambiguous outcome without recovery handles; preset casing was corrected and the corrected captured request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), so rendered TTS acceptance is unverified. This is preset/dialog/performance generation, not voice cloning. |
| [GET voices](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices) | email required, source system/user optional | Implemented bundled offline default and dynamic native system preset catalog in REST/SDK/CLI/MCP; same 30 names live verified. Project-scoped source=user saved-TTS inventory is wired across SDK/CLI/MCP/REST; account-wide completeness and final live adapter proof remain pending. |
| [GET voices/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices-ref) | Preset name or custom ref; fresh audio URL for user voice | Implemented selected system preset lookup/sample metadata. Saved user-TTS detail/fresh playback lookup is wired across SDK/CLI/MCP/REST; final live playback proof remains pending. |
| [DELETE voices/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-voices-ref) | Custom voice reference | Permanent selected saved-TTS deletion is wired across SDK/CLI/MCP/REST; final live lifecycle proof remains pending. System presets are not deletable. |
| [POST characters](https://useapi.net/docs/api-google-flow-v1/post-google-flow-characters) | displayName1–200, imageReference_1 required, optional second, personalityNotes≤2000, optional voice | Implemented project-scoped one/two-existing-image copy creation with notes and system preset metadata; owned saved-TTS voice binding is also wired with fresh ownership validation, pending final E2E; SDK/CLI/registered MCP/deployed HTTP lifecycle verified. Originals preserved. Legacy CLI create separately generates portraits; account-wide exact useapi semantics remain gaps. |
| [GET characters](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters) | email required | Implemented project-scoped native summaries in REST and shared SDK/CLI/MCP; live lifecycle/catalog reads verified. Not an account-wide inventory guarantee. |
| [GET characters/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters-ref) | Character ref; images/voice/thumbnail signed URLs | Implemented native detail with notes, image/workflow references and assigned preset metadata, live verified. Complete useapi signed image/voice/thumbnail URL response is not claimed. |
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
| Local Auto image aspect | CLI I2I, direct/queued MCP, REST managed references and run-config rows use nearest supported ratio from first decoded local reference; requested/resolved/policy retained. UUID-first without bytes and text/character-only Auto refuse. No Google AUTO enum. |
| Saved TTS CRUD | SDK/CLI/MCP/REST create/list/detail/delete; project-scoped visible owned audio, unknown completeness. One preview followed by metadata saves; not voice cloning. Corrected captured TTS request Google-rejected (gRPC 7); no audio or binding lifecycle accepted. |
| Saved-voice character binding | Fresh owned saved audio can be assigned through character create/update; metadata semantics separate from rendered speech. Final binding E2E pending. |
| Permanent individual media removal | Explicit operation=delete removes selected owned media rather than archiving siblings. Default whole-batch archive remains reversible. Owned fixture removal confirmed by a delayed metadata read; complete lifecycle BDD pending. Already-gone semantics remain different. |
| Standalone extension | SDK/CLI/MCP/REST identify and download independent extension outputs; available native model keys/costs discovered. Legacy scene-concatenating command remains separate. Paid acceptance pending. |
| Omni V2V | SDK/CLI/MCP/REST edit one owned source clip, explicit native model key/end frame, inherited aspect, at most5 existing images/3 saved voices. Virtual24fps start0–239/end1–240; default clip-end decoder absent. Paid acceptance pending. |
| Native R2V image/audio | SDK/CLI/MCP/REST use source-derived reference DTO, fresh model/tier/reference limits, native images and owned saved-audio UUIDs. Native model discovery passed live reads. One browser-token generation attempt returned PUBLIC_ERROR_UNUSUAL_ACTIVITY; no rendered output accepted. |
| Native credit inspection | Shared SDK/CLI/MCP returns source-defined total balance/paygate/service tier, unknown subscription/SKU null. Shared service adapters require explicit native host mode; native read-only E2E passed. |

Native model discovery is available for extension, edit and reference-video modes; all three passed actual read-only E2E. The registered MCP surface exposes35 tools.
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
- Video character/entity grounding and canonical positional image/entity/audio
  markers. Current R2V/audio attachments do not imply positional marker support.
- Native360p-to-720p promotion and video4K; three Pro subscriptions do not establish
  Ultra entitlements. Image2K is live verified; accepted image4K remains unverified.
- Arbitrary remote media and complete fresh signed image/character/voice/thumbnail
  resolution beyond currently supported managed/saved-TTS paths.
- Account-wide merged attached-media/history counts, account-wide character/voice
  inventories and full native library synchronization. Snapshot absence is not deletion.
- Exact already-gone individual-delete compatibility; registry/operator scope and
  native deletion acknowledgement remain distinct from useapi opaque IDs.
- Full ten-image model budgets: the measured Lite cap stays3; native-ID Auto
  dimensions, automatic source-duration/default V2V end resolution, and arbitrary
  uploaded audio/system-preset/character inputs on the dedicated V2V form.
- Successful live cookie-table import and automatic refresh are not established.
  Existing saved-profile reuse/project-access health proof is an observation, not
  a login-lifetime guarantee.

Unknown controls fail explicitly before generation. Local ffmpeg concatenate is
not a Google scene join. Local registration/cache removal is distinct from native
resource deletion. The fork has its own bare UUID/managed references; existing
useapi composite refs cannot be reused without a verified mapping. Job IDs,
protected callbacks and unknown outcomes preserve safe recovery identities and
never expose tokens, cookies or solver keys.

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

The native VIDEO_GENERATION CapSolver Enterprise v3 proxyless trial solved one token and submitted one count-one R2V request. Google rejected it with PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC 7: accepted outputs zero, rejected requests one, no retry. The earlier provider-image trial is separate. Combined measured production provider statistics are two solved tokens, two submitted requests, zero accepted outputs and two rejections. Provider acceptance is not proven. Current feature code remains a source checkpoint until publication; this is not full parity.

## Final measured lifecycle update

Permanent individual deletion passed its owned synthetic upload→delete lifecycle: one passed and four skipped in 28.91 seconds; all original active media remained active. The corrected canonical Charon TTS preview captured one no0P6 request and was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7): one failed and four skipped in 17.93 seconds. No audio or saved-voice binding lifecycle was accepted. Extension and edit generation were not additionally billed after the same account's reference-video/TTS refusals; their live model catalogs remain the proof, with rendered acceptance unverified.

The final CLI local-Auto attempt failed at shared migrated composer readiness with exit 25 (FlowAgentUiError): one failed and four skipped in 54.38 seconds, no accepted image. MCP received no additional paid retry after this shared blocker. CLI/MCP Auto remains offline-verified local aspect policy; native Google Auto is unsupported.
