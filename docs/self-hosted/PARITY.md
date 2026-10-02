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

Live baseline evidence available for text-to-image on the migrated host with two aspect ratios. Baseline image upscale was attempted and rejected before submission. Video generation and other account profiles have not been live verified in this deployment. Update this inventory alongside implemented adapter capabilities and verification evidence.

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
| [DELETE assets/email](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email) | `mediaGenerationIds` or `projectId` | Distinguish deleting local cached bytes from deleting Google project/media. Remote deletion unverified. |
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

The fork adds `gflow_cli.selfhost` with bearer-protected `/v1/google-flow` routes, per-profile serial workers, persistent SQLite jobs, idempotency keys, restart interruption semantics, image generation/local references, native image upscale dispatch, raw PNG/JPEG uploads, managed asset/download lookup, local project/media catalogue, accounts/read and callbacks. Callback destinations must be HTTPS allowlisted public hosts; private LAN callbacks are currently rejected. Query parameters that are not implemented return501 instead of being silently ignored.

Video text generation is disabled by default and requires explicit operator enabling. Native video1080p/original720p and270p GIF export adapters have been added; their deployment verification remains separate. Export downloads use local variant identifiers and retain the source media ID. Video extension currently returns501, because upstream scene output differs from useapi's standalone extension result. Custom voices, character REST operations, captcha solver routing, seed, automatic image aspect and account mutation remain unsupported. Unsupported fields and recognised inline slot markers fail before Google submission.

Image POST returns HTTP200 with a durable queued `jobId`, then clients poll GETjobs/jobId. This deliberately supports tee's HTTP200/polling path; it does not reproduce useapi's synchronous default for every caller. GIF export similarly uses a queued job/download path rather than synchronous `encodedGif`. GETprojects and GETmedia cover the local catalog/managed assets, not the full live Google library. An authenticated `/openapi.json` exposes the schema; interactive docs are disabled. These differences prevent describing the current adapter as a complete drop-in useapi replacement.

Static safety review verified managed-file containment, redacted subprocess failures, no shell execution of prompts, explicit unsupported request handling and413 for oversized JSON. Live image generation/upscale evidence must be recorded by the deployment operator before describing those routes as verified.

The adapter additionally exposes the bundled system voice catalog through GETvoices and GETvoices/ref. Custom voice generation/list/delete remains unsupported. Local FFmpeg video concatenation accepts2–10 managed MP4s from one profile, finite0–10s trims, and identical dimensions with square pixels. It normalises H.264/30fps and AAC/48kHz stereo, replacing absent audio with silence. This is a local equivalent, not a Google-side scene operation. Its queued result returns a managed artifact download and `encodedVideo` only within the20MiB inline limit. Local concatenations cannot be passed to Google native operations as though they had Google media IDs. Text-to-video count greater than1 returns501 until complete multi-output mapping exists.
