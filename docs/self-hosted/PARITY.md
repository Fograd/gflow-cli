# Google Flow / useapi parity inventory

Contract review: 2026-10-02. Baseline: upstream gflow-cli v0.82.1.
This is an implementation checklist, **not a claim of complete compatibility**.
A CLI command existing does not prove its migrated `flow.google.com` transport works.
Native Google upscaling is distinct from resizing with an image library.

## Evidence and status vocabulary

- **CLI**: a baseline command exists; adapter and live verification remain separate.
- **Migrated unported**: upstream explicitly rejects or has not ported this form; absence in gflow is not evidence that Google's UI cannot do it.
- **Missing**: no equivalent public CLI command found.
- **Local equivalent**: an implementation can reproduce the output locally, but does not perform the same Google-side operation.

Live baseline evidence available for text-to-image on the migrated host with two aspect ratios. Historical upstream baseline image upscale was rejected before submission; the fork supersedes that baseline with live-verified native2K CLI/HTTP/MCP results recorded below and in VERIFICATION.md. Video generation and other account profiles have not been live verified in this deployment. Update this inventory alongside implemented adapter capabilities and verification evidence.

## Endpoint contract inventory and historical upstream baseline

All paths below use the useapi `/v1/google-flow` prefix; all calls require bearer authentication. Links are authoritative contract references. The final column records the historical upstream baseline and original work checklist, except where an explicit current expansion note appears. Current implemented scope and proof obligations are summarized below; a baseline “unported” entry is not a current fork refusal.

| Endpoint | Request contract / result | Baseline and work required |
|---|---|---|
| [POST accounts](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts) | Cookie-table import; account configuration and refresh information | Private cookie-table import and staged identity/project access checks are implemented; rejected clone proof exists, successful live import remains pending. Credential values are deliberately not echoed. |
| [GET accounts](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts) | Object keyed by account email with health/configuration | Profile store exists; adapter must redact secrets and expose registered profile health. |
| [GET accounts/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-email) | Account details for path email | Local configured-account mapping required. |
| [DELETE accounts/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-accounts-email) | Remove registered account | Adapter should unregister configuration separately from deleting a browser profile; reject while busy. |
| [POST accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts-captcha-providers) | Provider keys; empty key removes provider; masked response | Missing hosted solver routing. Browser page-owned captcha works for baseline image generation. Keys must remain in secret storage. |
| [GET accounts/captcha-providers](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-providers) | Masked configured provider metadata | Must not imply configured keys are connected to transport before actual integration. |
| [GET accounts/captcha-stats](https://useapi.net/docs/api-google-flow-v1/get-google-flow-accounts-captcha-stats) | Solver usage / acceptance statistics | Missing; browser attempts must be labelled separately from solver attempts. |
| [POST assets/email](https://useapi.net/docs/api-google-flow-v1/post-google-flow-assets-email) | Raw content with MIME header; image or MP4 upload; account pinned | CLI image upload; migrated local-file I2I uploads internally. Adapter can store image references locally and upload at generation, but must label local IDs and reject unsupported video upload. |
| [GET assets/mediaGenerationId](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-mediagenerationid) | Path opaque media reference; optional `raw`; metadata or bytes | Local result registry/download equivalent; full remote asset lookup separately requires transport. |
| [GET assets/projects/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-projects-email) | Account projects; optional cursor pagination | CLI project surface exists; migrated project listing needs verification. |
| [GET assets/media/email](https://useapi.net/docs/api-google-flow-v1/get-google-flow-assets-media-email) | Project media; optional `projectId` | CLI project/media surface; full migrated library inventory not verified. Local result list is not full Google library. |
| [DELETE assets/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email) | Required `mediaGenerationIds`1–100 image/video IDs; optional `projectId`; validate the whole batch first | Distinguish deleting local cached bytes from deleting Google project/media. Remote deletion unverified. |
| [POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) | See image parameter matrix | CLI T2I and local-file I2I supported on migrated host. Historical baseline: UUID/entity references were unported. The current isolated expansion adds immutable image slot plans and fresh weighted entity preflight; live positional transport proof is tracked separately. |
| [POST images/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images-upscale) | `mediaGenerationId`, `resolution` default2k; captcha controls; encoded JPEG | CLI exists for labs; migrated unported at baseline. Native2k is priority. 4k requires Ultra, so Pro profiles must be refused early. |
| [POST videos](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) | See video parameter matrix | CLI T2V/local-file I2V/R2V; selected modes migrated. Omni/V2V and named/UUID/entity references not blanket supported. |
| [POST videos/upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-upscale) | `mediaGenerationId`; resolution720p/1080p/4K default1080p; async/callback/captcha | Missing public command. 4K requires Ultra; 720p/1080p paid plans. Genuine native operation needs port. |
| [POST videos/gif](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-gif) | `mediaGenerationId`; synchronous `encodedGif` | Missing public command; local ffmpeg equivalent feasible and should be labelled. |
| [POST videos/extend](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-extend) | `mediaGenerationId`, `prompt`, `model`, count1–4, seed, async/callback/captcha | CLI extend exists; migrated unported. Veo only; source aspect inherited. |
| [POST videos/concatenate](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-concatenate) | `media`2–10 items: ID, trimStart/trimEnd0–10s; sum trims less than clip duration; encodedVideo | CLI scenes/movie composition related; migrated scenes unported. Local ffmpeg equivalent requires matching aspects and account provenance checks. |
| [POST voices](https://useapi.net/docs/api-google-flow-v1/post-google-flow-voices) | email, preset voice, dialog1–120 chars, voicePerformance1–120, displayName1–200, captcha | Missing custom voice creation command. Preset voices lookup exists. |
| [GET voices](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices) | email required, source system/user optional | CLI preset lookup only; custom voice inventory missing. |
| [GET voices/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-voices-ref) | Preset name or custom ref; fresh audio URL for user voice | Static preset sample equivalent; custom signed playback missing. |
| [DELETE voices/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-voices-ref) | Custom voice reference | Missing. Must not delete system presets. |
| [POST characters](https://useapi.net/docs/api-google-flow-v1/post-google-flow-characters) | displayName1–200, imageReference_1 required, optional second, personalityNotes≤2000, optional voice | CLI create supported migrated; reference mapping and live verification required. |
| [GET characters](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters) | email required | CLI list exists but migrated reads retired labs route at baseline. |
| [GET characters/ref](https://useapi.net/docs/api-google-flow-v1/get-google-flow-characters-ref) | Character ref; images/voice/thumbnail signed URLs | CLI show exists; migrated lookup unverified. |
| [DELETE characters/ref](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-characters-ref) | Character ref | CLI rm exists; migrated unverified. |
| [GET jobs](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs) | options, executing, completed, failed, rateLimited filters | Upstream queued worker exists; adapter needs its own durable jobs and explicit status mapping. |
| [GET jobs/jobid](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs-jobid) | Job identifier; status, request/response/error | Durable adapter record; redact request secrets and retain same ID through completion. |

## Image parameters

| Parameter | useapi contract | Adapter requirement |
|---|---|---|
| prompt | Required | Validate before acquiring profile or submitting. |
| model | nano-banana-2-lite default, nano-banana-2, nano-banana-pro | Map to CLI model IDs explicitly. |
| aspectRatio |16:9,4:3,1:1,3:4,9:16; auto only with references | Map explicit ratios; never substitute auto silently. |
| count / seed | count1–4 default4; seed nonnegative integer | Honour count; reject seed if chosen transport cannot enforce it. |
| email | Optional; healthy account selection | Pin refs to source account and serialize each profile. |
| reference_1…10 | Uploaded/generated image opaque refs | Resolve local refs to files for migrated I2I; cross-account references must fail. |
| character_1…7 | Shares image reference budget | Implemented native image entity attachment with one fresh owned-project read and actual image-workflow weights. Canonical SDK live image proof passes; HTTP/CLI slot wrappers have offline codec proof but no separate live generation proof yet. |
| inline @ markers | Known slot grounding, case-insensitive, supplied slot required | Image slot mode preserves ordered literal/reference spans and repeated chips, with deduplicated attachment vectors checked before dispatch. Missing reserved image slots fail400; unknown token families remain literal. Canonical video positional grounding is still unimplemented. |
| replyUrl / replyRef | Job callbacks and caller reference | Allowlisted destinations, bounded timeouts, durable terminal delivery; callback failure must not resubmit generation. |
| captchaToken / captchaRetry / captchaOrder | Mutually exclusive controls | Reject unless transport implements them; never pretend browser mint consumed supplied token. |

## Video parameters

[POST videos contract](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos).

Core: prompt; model(`veo-3.1-fast` default, quality, lite, lite-low-priority, omni-flash); aspectRatio(landscape/portrait; extra ratios Veo only); duration4/6/8/10 per model; resolution360p/720p(360p Omni only); count1–4(default1); nonnegative seed; optional email. References: startImage/endImage, referenceImage_1…7, character_1…7, referenceAudio_1…5, referenceVideo_1 with startFrameIndex_1(0–239)/endFrameIndex_1(1–240) on virtual24fps timeline. Async defaultfalse, replyUrl/replyRef, captcha controls.

Frames require start before end and cannot mix with ingredients. Veo ingredients exclude Quality, use8s and max3 images; Omni ingredients max7 images/5voices and supports V2V edits. Character images consume image budget. V2V duration follows trim window, no duration option. Inline supported image/character/audio markers require their slots; inline video marker unsupported. Validate every model/mode combination before billing. Baseline does not implement this entire parameter cross-product.

## Shared response and error requirements

Never reuse useapi opaque identifiers as though they were raw Google UUIDs. Own references need a durable registry containing Google media ID, profile, project, kind and local bytes location. Existing useapi refs cannot be imported without a verified mapping.

Implement idempotency at job creation. After process restart, a job that may have submitted to Google must be marked interrupted and reconciled, not automatically resubmitted. Persist results before emitting completed callbacks. Never include cookies, bearer tokens, raw captcha tokens or solver keys in responses, logs or persisted public request objects.

Unsupported endpoint/options: explicit501 with capability reason before Google submission. Invalid request400, authentication401, unknown reference404, profile busy/cooldown429 with Retry-After. Preserve upstream quota/model/captcha distinctions where genuinely measured; generic exit text is not a verified quota diagnosis.

## Historical tee client comparison

This historical read-only comparison describes the old client, not the current service contract. No tee changes are part of this work. Current synchronous requests return200 only when completed and408 with a durable job identity when still processing; explicit asynchronous requests return201. See [HTTP job semantics](HTTP_JOB_SEMANTICS.md). Original observations:

1. Base URL is hardcoded. Add a configuration override to point at this service; do not switch production until live image and upscale verification passes.
2. Generation POST must return HTTP200 by default. Tee rejects201/202. The historical client allowed HTTP200 created responses with `jobId`; the current service uses408 for unfinished synchronous work; completed response must include `media`.
3. Image bytes use `media[0].image.generatedImage.encodedImage`. Do not emit an HTTP localhost `fifeUrl`; tee rejects URLs outside approved Google HTTPS hosts.
4. Raw upload accepts MIME header. Response must include `mediaGenerationId: {mediaGenerationId: REF}` and `email` for account pinning. Add `/assets` convenience route because tee calls it without account initially.
5. GET accounts must return an object keyed by account handle with `health: "OK"` for enabled, usable profiles. Authentication cookie presence alone is not live health.
6. Reference generation currently returns the uploaded input reference as `GeneratedImage.media_generation_id`. Adapt tee to take generated output ID from the response before feeding it into upscale.
7. Existing transport90s timeout means long operations require a client that retains the408 job identity and polls, or requests asynchronous201 explicitly. Retrying on HTTP errors must never duplicate already accepted work.

Recommended compatibility prefix: `/v1/google-flow`, alongside capability discovery and OpenAPI. Existing `/mcp` stays independent. A non-useapi extension may expose `/api/v1/capabilities`, health and direct local downloads. Document differences instead of claiming drop-in compatibility for unimplemented fields.

## Architecture and UX review

**CAUTION, confidence8/10.** Authenticated REST adapter plus durable SQLite jobs is appropriate for one user with multiple profiles. It should call application operations or a controlled CLI subprocess boundary, not insert HTTP server concerns into Playwright transport. Upstream PLAN explicitly excludes hosting/multi-tenancy; this fork deliberately adds single-user hosting and should document that scope.

Required mitigations: bound input/output sizes and job concurrency; use profile leases across CLI/MCP/REST processes; bind loopback by default with explicit private network exposure; secret redaction; callback allowlist and no redirects; persisted idempotency; restart interruption semantics; explicit unsupported-option errors. Three paid plans increase aggregate allowance after each is logged in, not native resolution entitlements or safe concurrency within one profile. Add visible capability and verification labels so API consumers can distinguish implementation from live-tested support.

This deployment-specific document is intentionally not mirrored into the upstream public website.

## Fork adapter implementation snapshot

The fork implements authenticated REST, durable SQLite jobs, bounded synchronous
waiting, explicit HTTP 201 async responses, sticky idempotency, per-profile serial
workers, callbacks and interruption handling. Synchronous unfinished work returns
HTTP 408 with its original job identity and processingContinues; the worker
continues without replay. The default wait is 600 seconds, with a 180-second
concatenation ceiling. Public GET/callback status is started for running work;
interrupted submissions expose outcomeUnknown and retryable false. See
[HTTP job semantics](HTTP_JOB_SEMANTICS.md).

Image text/reference generation, native2K dispatch, raw PNG/JPEG/MP4 upload, managed downloads and bundled system voices are available. Native image seed overrides use consecutive seeds for batches; supplied-token image rewriting is implemented but live acceptance is unproven. Native reload metadata is measured, but provider generation is guarded with HTTP 501 pending actual third-party acceptance. Fresh same-page replacement and one actual paid CapSolver solution were rejected by Google unusual activity; actual trial counters1solved/1submitted/0accepted, no retry. Key configuration/statistics remain available. Configuration availability is not proof of a functioning live solver path. Read [SEEDS.md](SEEDS.md), [CAPTCHA.md](CAPTCHA.md) and [verification](VERIFICATION.md) for proof boundaries; configured solver keys alone do not prove Google acceptance. Native action metadata is measured; supplied-token live acceptance remains unverified.

Video adapters cover text, start/end images and image ingredients with validated model restrictions, serial count1–4 output checkpoints and optional Omni360p/720p. They remain disabled by default and paid live generation is unverified. Native1080p/original720p/GIF exports are separate from resolution promotion. Extension, V2V, voice/entity/audio grounding and video CAPTCHA overrides remain unsupported.

Local account POST/DELETE handles existing saved profiles and explicit operator attestation; staged cookie import/refresh is now implemented with identity/access verification before activation, while local registration deletion preserves browser profiles. Job filters/pagination, asset raw bytes, managed-media project filtering and local project pagination are implemented. Explicit localOnly asset deletion validates owned, inactive references, then removes cache records/bytes; it does not delete Google assets. Explicit source=google now reads the selected-project authoritative timeline; native archive queues a reversible whole-batch Google operation. It requires all siblings, explicit projectId and distinct owned UUIDs. Native source=google account project discovery now supports fixed 21-item pages and opaque continuation, measured with two disjoint pages. Full merged library/history counts and exact individual/idempotent deletion semantics remain gaps.

Local FFmpeg concatenation validates2–10 owned managed clips and produces a local artifact ID. It is not a Google-side scene operation. Public capability discovery/OpenAPI require bearer auth. These explicit differences prevent claiming complete drop-in useapi compatibility.

## Remaining parity work and proof obligations

Every endpoint above is accounted for. These groups explain why a gap remains and the next concrete action; they are not claims that the Google frontend lacks the feature.

| Gap | Evidence / boundary | Next action |
|---|---|---|
| Account cookie import and session refresh | Private staged import/refresh validates actual identity and Flow project access before activation; original profiles/registration survive refusal. Cookie presence alone is insufficient. | Offline integration and rejected-clone proof pass; accepted live import pending. Credential echo is intentionally omitted. |
| Full project/media inventories | Local catalogues remain default; native account discovery reads 21-item pages and selected-project timeline reads are available. useapi project listing aggregates history counts and media listing merges attached media, still different. | Native UpteDb paging is measured (21+21 disjoint); retain opaque cursor and verify REST wiring. Measure history counts/attached-media merging separately; do not infer uploaded status from an absent prompt. |
| Native media deletion | Local cache deletion and reversible native whole-batch archive now exist. useapi individual/already-gone semantics differ. | Retain whole-batch ownership validation and measured archive acknowledgement; add individual/already-gone compatibility only after capture. Synthetic upload/list/archive is live verified without generation credits. |
| Native character CRUD | Project-scoped summary/detail and metadata patch/delete are implemented; one/two-reference POST has native create/copy and deployed HTTP lifecycle proof. Initial notes are now validated and applied after reference copy; system preset assignment is now measured; account-wide useapi semantics remain gaps. The SDK/CLI/MCP now share native existing-image creation/list/detail/update/removal; the older create command separately generates portraits. | Capture migrated character list/create/patch/delete and bind supplied owned references with optional voice. Keep local metadata separate from Google-side records. |
| Character generation binding | Canonical native image SDK proof now passes with one entity, repeated media positions, fresh weighted ownership and one accepted square image. Native no-replay/unknown acknowledgement handling is implemented. | Separately prove HTTP/CLI/MCP slot-wrapper accepted generation; preserve source identity and known output handles. Video character grounding and rendered speech remain unverified. |
| Custom voice CRUD | Both bundled and dynamic native system presets (30 measured) are available; custom TTS generation, signed playback and delete remain separate operations. | Capture custom voice creation/list/detail/delete, validate preset/dialog/performance limits and prove real token consumption where captcha is required. |
| Native seed verification | Image overrides now target native ogiZ0b seed slots; aborted browser capture verifies the outgoing value. | Live REST two-image batch returned the requested consecutive seeds and decoded images; retain ledger evidence. Video seed remains unported. |
| Automatic image aspect | Implemented REST managed-local-reference policy derives the first numeric image reference’s nearest supported ratio; CLI/MCP Auto remain gaps; no Google AUTO enum is claimed. | Preserve requested/resolved/aspectPolicy metadata and reference order. Historical inconclusive chooser capture is superseded by the explicit approximation, not by a native automatic-mode claim. |
| Inline markers and entity/audio inputs | Image parser, native composer and actual outgoing entity/media vectors are implemented and native SDK acceptance is verified. Audio/video positional grounding remains separate. | Retain immutable queue plans and weighted preflight; add separate HTTP/CLI/MCP accepted-generation proof and measured video/audio wire contracts. |
| Multi-video live proof | Adapter now serialises count1–4 single-output calls and checkpoints results. | Verify paid multi-output generation/partial failure on Google; never automatically replay checkpointed submissions. |
| OmniV2V, voice references and trim windows | Models support different frame/reference modes; pass-through fields would silently change behaviour. | Reuse observed edit/reference RPCs, verify24fps trim semantics and prohibit incompatible start/end/ingredients combinations before submit. |
| Video extension | Upstream CLI combines scenes; useapi returns an individual new extension segment. | Capture standalone Veo extension on migrated host and return the new segment ID/path. Do not relabel the source ID with a concatenated scene output. |
| Native360p→720p promotion /4K | Baseline720p export downloads the original; it does not prove promotion. Three Pro plans do not grant Ultra4K. | Measure the actual promotion operation. Verify4K only with an Ultra profile; retain verified Pro refusal as entitlement evidence. |
| Solver configuration / supplied tokens | A key stored locally is not proof that generation uses it; page-owned minting may ignore externally supplied tokens. | Integrate private providers with bounded retries and accurate statistics, then verify the selected token reaches the real Google request. Credentials and successful-provider samples require operator setup. |
| Exact synchronous/async contract | HTTP 201 async and completed HTTP 200 synchronous responses; unfinished synchronous work returns HTTP 408 with durable identity and processingContinues. GET/callback projection shares statuses, timestamps and response.media. | Offline/local HTTP proof and deployed production health/job projection proof exist. Representative video generation/export acceptance and timeout behavior remain separately unverified; health proof does not establish paid-video parity. |
| Native lifecycle semantics | Typed job filters/pagination/raw bytes and local registration/cache deletion exist. | Verify native Google lifecycle separately; retain local scope labels and active-job guards. |

Captures remain private because browser requests contain cookies, tokens and user prompts. Public findings should name operations, redacted RPC shapes and verification results, not logged-in identities or project IDs. API and capability documentation must change in the same patch as each implemented operation. Successful live evidence belongs in [the verification ledger](VERIFICATION.md); current usage and deployment instructions are indexed in [the fork documentation](INDEX.md).

Current native read expansion also exposes GETcharacters project summaries and catalog=google dynamic system voices. Native detail/metadata PATCH/DELETE are present, while one/two-reference POST is implemented and live verified; they do not enable full custom voice CRUD or rendered speech. Image entity grounding is now live verified through the canonical native SDK path; portable wrapper acceptance remains separately unverified. Live adapter wiring and worker evidence are separate in VERIFICATION.md.

Limited deployed HTTP character CRUD is live verified: one copied owned image, initial/PATCH notes, detail persistence, deletion/404 and preserved original source. Second reference is now live verified in portrait/body slots; system preset assignment is now measured, while preset-rendered speech and video generation binding remain separate gaps.


## Preset assignment: current proof and historical probe

Native system preset assignment is implemented and measured. Native adapter,
deployed HTTP and portable CLI/MCP metadata lifecycle proofs retain Charon,
change it to Aoede and preserve the chosen preset when clearing personality
notes. Rendering speech is a separate unverified operation.

The earlier empty-dialogue preview probes did not commit voice metadata and
were cleaned up without TTS generation. Those historical failures were
superseded by the later metadata assignment proof; they do not contradict
current assignment support. Custom saved-voice CRUD and rendered speech still
require separate contracts and proof. See
[the historical picker spike](../superpowers/spikes/2026-10-02-native-voice-picker-transition.md).

## Portable native SDK/CLI/MCP expansion

The current native SDK supports existing-image character create/list/detail/
update/delete and explicit native project/media snapshots. CLI and registered
MCP adapter mirrors are live verified separately: two existing references,
initial notes/Charon, notes clear, renamed/new notes/Aoede, readback and exact
identity removal; project page IDs and mixed media kinds match across both
surfaces. Three adapter scenarios passed in 265.40s. The strengthened SDK native
inventory BDD passed separately in 11.42s with 21+21 disjoint native pages and
unknown completeness. These are direct bounded native operations, without
queued mutation replay or full local catalog synchronization. Dynamic native voice listing is implemented in SDK, CLI and MCP in the isolated expansion; read-only SDK/CLI/MCP mirror proof passed with the same 30 preset names in 27.05s, without generation or mutation. Bundled CLI/MCP voice listing remains the offline default.
Image character grounding is accepted through the canonical native SDK path. Separate HTTP/CLI/MCP slot acceptance, video character grounding, rendered speech and custom voices remain proof obligations or gaps.

## Current image reference expansion

Image-only canonical slot mode accepts case-insensitive `@reference_1..10` and `@character_1..7`, requires each matching supplied slot, preserves repeated positions and literal unknown families, and retains unmentioned attachments. CLI/MCP opt in with `reference_syntax=slots`; existing named-reference behavior remains the default. HTTP image fields select canonical slot mode. Queued private DTOs reconstruct the immutable plan instead of passing stripped text to a legacy command. Managed upload IDs are logical identities until native upload acknowledgement supplies the Google identity. Fresh native ownership and actual character image workflows determine the weighted image budget before billing; the measured Lite cap remains 3. Native composer accepted proof passed: one square 1024×1024 JPEG, exact repeated-media/entity positions and deduplicated vectors, one dispatch and owned entity cleanup. This is canonical native SDK proof; HTTP/CLI/MCP slot wrappers are not separately live verified. Canonical video positional grounding remains unimplemented.

REST Auto aspect for managed local image references is implemented as a labelled approximation derived from the first numeric reference, using the nearest supported ratio. CLI/MCP Auto and native Google Auto remain gaps; no Google AUTO sentinel is claimed.


Current native image picker limitation: a direct reference and a copied character workflow can retain the same caption. The caption-ambiguity guard then refuses before submission even though both identities are owned. This is a fork picker compatibility limit, not evidence that Google forbids the combination. The first CLI adapter probe after hydration encountered this safe refusal, generated zero images and cleaned its owned character. Canonical SDK proof remains valid; portable wrapper acceptance is still separately tracked.

Three CLI image adapter attempts have now refused safely before submission: initial hydration, same-caption ambiguity and an active owned reference absent from the visible picker grid. They generated zero images and cleaned their owned fixtures. Fresh project ownership alone does not guarantee that the picker exposes the selected asset. These are measured fork adapter limits; they do not prove Google lacks the requested feature.
