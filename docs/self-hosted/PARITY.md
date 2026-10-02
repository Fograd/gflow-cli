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

## Endpoint inventory

All paths below use the useapi `/v1/google-flow` prefix; all calls require bearer authentication. Links are authoritative contract references.

| Endpoint | Request contract / result | Baseline and work required |
|---|---|---|
| [POST accounts](https://useapi.net/docs/api-google-flow-v1/post-google-flow-accounts) | Cookie-table import; account configuration and refresh information | CLI interactive auth exists. Self-hosted profile registration is safer; cookie import and response exposing cookies deliberately not equivalent. |
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
| [POST images](https://useapi.net/docs/api-google-flow-v1/post-google-flow-images) | See image parameter matrix | CLI T2I and local-file I2I supported on migrated host. UUID/entity references unported. |
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
| character_1…7 | Shares image reference budget | Migrated entity attachment unported; fail before submit. |
| inline @ markers | Known slot grounding, case-insensitive, supplied slot required | Rewrite into actual entity grounding only when supported; reject unsupported markers rather than literalizing them. |
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

## Tee pipeline compatibility

Read-only inspection of `app/useapi_google_flow.py` found these concrete contracts:

1. Base URL is hardcoded. Add a configuration override to point at this service; do not switch production until live image and upscale verification passes.
2. Generation POST must return HTTP200 by default. Tee rejects201/202. A HTTP200 created response with `jobId` can be polled; completed response must include `media`.
3. Image bytes use `media[0].image.generatedImage.encodedImage`. Do not emit an HTTP localhost `fifeUrl`; tee rejects URLs outside approved Google HTTPS hosts.
4. Raw upload accepts MIME header. Response must include `mediaGenerationId: {mediaGenerationId: REF}` and `email` for account pinning. Add `/assets` convenience route because tee calls it without account initially.
5. GET accounts must return an object keyed by account handle with `health: "OK"` for enabled, usable profiles. Authentication cookie presence alone is not live health.
6. Reference generation currently returns the uploaded input reference as `GeneratedImage.media_generation_id`. Adapt tee to take generated output ID from the response before feeding it into upscale.
7. Existing transport90s timeout means long sync operations need HTTP200 accepted job with polling, or a longer timeout. Retrying on HTTP errors must never duplicate already accepted work.

Recommended compatibility prefix: `/v1/google-flow`, alongside capability discovery and OpenAPI. Existing `/mcp` stays independent. A non-useapi extension may expose `/api/v1/capabilities`, health and direct local downloads. Document differences instead of claiming drop-in compatibility for unimplemented fields.

## Architecture and UX review

**CAUTION, confidence8/10.** Authenticated REST adapter plus durable SQLite jobs is appropriate for one user with multiple profiles. It should call application operations or a controlled CLI subprocess boundary, not insert HTTP server concerns into Playwright transport. Upstream PLAN explicitly excludes hosting/multi-tenancy; this fork deliberately adds single-user hosting and should document that scope.

Required mitigations: bound input/output sizes and job concurrency; use profile leases across CLI/MCP/REST processes; bind loopback by default with explicit private network exposure; secret redaction; callback allowlist and no redirects; persisted idempotency; restart interruption semantics; explicit unsupported-option errors. Three paid plans increase aggregate allowance after each is logged in, not native resolution entitlements or safe concurrency within one profile. Add visible capability and verification labels so API consumers can distinguish implementation from live-tested support.

This deployment-specific document is intentionally not mirrored into the upstream public website.

## Fork adapter implementation snapshot

The fork implements authenticated REST, durable SQLite jobs, bounded synchronous waiting (default85seconds), explicit async immediate responses, sticky idempotency, per-profile serial workers, callbacks and interruption handling. Both response modes use HTTP200, so explicit async201 parity remains a documented difference. A timeout returns the original job; it never resubmits Google work.

Image text/reference generation, native2K dispatch, raw PNG/JPEG/MP4 upload, managed downloads and bundled system voices are available. Native image seed overrides use consecutive seeds for batches; supplied CAPTCHA token/provider hooks are implemented for images only, but live metadata capture and third-party-token acceptance remain unverified. Configuration availability is not proof of a functioning live solver path. Read [SEEDS.md](SEEDS.md), [CAPTCHA.md](CAPTCHA.md) and [verification](VERIFICATION.md) for proof boundaries; configured solver keys alone do not prove Google acceptance. Provider generation controls are guarded501 before queueing until the native action is measured; supplied-token live acceptance remains unverified.

Video adapters cover text, start/end images and image ingredients with validated model restrictions, serial count1–4 output checkpoints and optional Omni360p/720p. They remain disabled by default and paid live generation is unverified. Native1080p/original720p/GIF exports are separate from resolution promotion. Extension, V2V, voice/entity/audio grounding and video CAPTCHA overrides remain unsupported.

Local account POST/DELETE handles existing saved profiles and explicit operator attestation; it neither imports cookies nor deletes browser profiles. Job filters/pagination, asset raw bytes, managed-media project filtering and local project pagination are implemented. Explicit localOnly asset deletion validates owned, inactive references, then removes cache records/bytes; it does not delete Google assets. Explicit source=google now reads the selected-project authoritative timeline; native archive queues a reversible whole-batch Google operation. It requires all siblings, explicit projectId and distinct owned UUIDs. Full merged library/history and exact individual/idempotent deletion semantics remain gaps.

Local FFmpeg concatenation validates2–10 owned managed clips and produces a local artifact ID. It is not a Google-side scene operation. Public capability discovery/OpenAPI require bearer auth. These explicit differences prevent claiming complete drop-in useapi compatibility.

## Remaining parity work and proof obligations

Every endpoint above is accounted for. These groups explain why a gap remains and the next concrete action; they are not claims that the Google frontend lacks the feature.

| Gap | Evidence / boundary | Next action |
|---|---|---|
| Account cookie import and session refresh | Existing fork uses operator-verified Chrome profiles. Cookie presence alone does not prove usable Flow access. | Local profile registration/unregistration and attestation are implemented; useapi cookie-table import still needs a separate private import/validation path. Never return credential values. |
| Full project/media inventories | Local catalogues are a subset. useapi project listing groups media-history scans by project; media listing merges timeline and attached media. | Measure migrated project/history/catalogue RPCs, cursor semantics and provenance. Preserve per-page counts; do not infer uploaded status from an absent prompt. |
| Native media deletion | Local cache deletion and reversible native whole-batch archive now exist. useapi individual/already-gone semantics differ. | Retain whole-batch ownership validation and measured archive acknowledgement; add individual/already-gone compatibility only after capture. Synthetic upload/list/archive is live verified without generation credits. |
| Native character CRUD | Upstream list/show use a retired labs listing. Its create command generates references instead of binding the existing1–2image references required by useapi. | Capture migrated character list/create/patch/delete and bind supplied owned references with optional voice. Keep local metadata separate from Google-side records. |
| Character generation binding | The migrated picker has measured entity chips and accepted submissions, but null submit payloads break the observer. | Add project-keyed status fallback and durable accepted-output checkpoints before enabling the guarded path. Do not equate a timeout with Google rejection. |
| Custom voice CRUD | System presets are bundled; custom TTS generation, signed playback and delete are separate operations. | Capture custom voice creation/list/detail/delete, validate preset/dialog/performance limits and prove real token consumption where captcha is required. |
| Native seed verification | Image overrides now target native ogiZ0b seed slots; aborted browser capture verifies the outgoing value. | Live REST two-image batch returned the requested consecutive seeds and decoded images; retain ledger evidence. Video seed remains unported. |
| Automatic image aspect | Existing aspects are explicit. Inferring an aspect from reference dimensions is not proof of native automatic mode. | Observe native auto handling; if providing local inference, label that difference and use the first owned reference consistently. |
| Inline markers and entity/audio inputs | Literal text is not grounded reference attachment. | Resolve case-insensitive known markers to supplied slots, validate model reference budgets and assert outgoing entity/media/audio IDs before billing. |
| Multi-video live proof | Adapter now serialises count1–4 single-output calls and checkpoints results. | Verify paid multi-output generation/partial failure on Google; never automatically replay checkpointed submissions. |
| OmniV2V, voice references and trim windows | Models support different frame/reference modes; pass-through fields would silently change behaviour. | Reuse observed edit/reference RPCs, verify24fps trim semantics and prohibit incompatible start/end/ingredients combinations before submit. |
| Video extension | Upstream CLI combines scenes; useapi returns an individual new extension segment. | Capture standalone Veo extension on migrated host and return the new segment ID/path. Do not relabel the source ID with a concatenated scene output. |
| Native360p→720p promotion /4K | Baseline720p export downloads the original; it does not prove promotion. Three Pro plans do not grant Ultra4K. | Measure the actual promotion operation. Verify4K only with an Ultra profile; retain verified Pro refusal as entitlement evidence. |
| Solver configuration / supplied tokens | A key stored locally is not proof that generation uses it; page-owned minting may ignore externally supplied tokens. | Integrate private providers with bounded retries and accurate statistics, then verify the selected token reaches the real Google request. Credentials and successful-provider samples require operator setup. |
| Exact synchronous/async contract | Bounded default85second waiting and explicit async are implemented; both return200 and long operations return the same durable job. | Decide whether to add opt-in useapi201 and timeout/error compatibility without breaking tee200 consumers. |
| Native lifecycle semantics | Typed job filters/pagination/raw bytes and local registration/cache deletion exist. | Verify native Google lifecycle separately; retain local scope labels and active-job guards. |

Captures remain private because browser requests contain cookies, tokens and user prompts. Public findings should name operations, redacted RPC shapes and verification results, not logged-in identities or project IDs. API and capability documentation must change in the same patch as each implemented operation. Successful live evidence belongs in [the verification ledger](VERIFICATION.md); current usage and deployment instructions are indexed in [the fork documentation](INDEX.md).
