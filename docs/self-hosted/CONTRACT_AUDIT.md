# UseAPI Flow contract audit

Audit baseline: `ff42c17c`, 2026-10-04. Read-only comparison of all 29 primary endpoint documents cached from official UseAPI documentation on 2026-10-03 against the self-hosted adapters. This is a source contract audit, not evidence that Google accepted every generation. Subsequent fixes must be recorded against their own revision.

Paths below are relative to `/v1/google-flow`. “Implemented” means an adapter exists; native entitlement, ownership, CAPTCHA acceptance and rendered output still require the separate live evidence ledger. Vendor-shaped opaque IDs require explicit exact local registration; their prefixes never prove ownership.

## Endpoint matrix

| # | Official endpoint | Official controls | Baseline implementation and concrete differences |
|---|---|---|---|
| 1 | POST /accounts | cookies table | Verified staged cookie import exists; additionally supports operator profile/email/projectId/enabled/verified. Response is local account metadata, not vendor cookie/session/refresh envelope. |
| 2 | GET /accounts | none | Email-keyed local registration summaries. Vendor health/backend/session expiry/nextRefresh fields are not automatically probed here. Separate health POST exists. |
| 3 | GET /accounts/{email} | email | Local registration metadata; does not return fresh credits/models or vendor refresh schedule. Existing native credit/model reads are separate surfaces. |
| 4 | DELETE /accounts/{email} | email | Removes local registration, preserves browser profile, rejects busy accounts. Explicit local scope differs from vendor account teardown envelope. |
| 5 | POST /accounts/captcha-providers | optional provider keys; empty string removes | CapSolver and 2Captcha only. Five other vendor providers intentionally absent; user selected CapSolver. No provider acceptance claim follows from saving a key. |
| 6 | GET /accounts/captcha-providers | none | Masked configured supported keys. Vendor freeCaptchaCredits subsidy is not a self-hosted feature. |
| 7 | GET /accounts/captcha-stats | date, limit≤50000, provider, anonymized | Local aggregate phase counters only. Query controls are not applied; timestamped rows, date windows, tier/SKU/status buckets and latency averages absent. Vendor global anonymized sample cannot be reproduced from local observations. |
| 8 | POST /assets/{email} (email optional) | raw PNG/JPEG/WebP/MP4, optional account | PNG/JPEG/MP4 implemented; WebP absent. MP4 requires explicit rights header. Twenty MiB cap and local job envelope differ from full vendor media/workflow upload DTO. |
| 9 | GET /assets/{mediaGenerationId} | raw=true or1 | Fresh exact image/video read via UUID with explicit account/project or registered alias. Signed-URL JSON and validated PNG/JPEG/MP4 raw supported; cached-file retrieval is separate. Arbitrary vendor IDs are not decoded. |
| 10 | GET /assets/projects/{email} | cursor | Default generated-history summaries now match per-call project counts, byType, dates, scanned/truncated/cursor/timeBudget. Explicit google catalog/local project extensions remain. Bounded native projection excludes unproven origins, completeness unknown. |
| 11 | GET /assets/media/{email} | projectId optional | Default native whole-project timeline/attached inventory with source times and upload marker. Origin project/attachment distinction retained. IDs remain UUIDs unless explicitly registered aliases. Local cache is explicit source=local. |
| 12 | DELETE /assets/{email} | mediaGenerationIds1–100, optional projectId | Permanent deletion and confirmed already-gone receipts implemented. Raw UUIDs only; composite input mapping absent. Native deletion requires selected exact project, while vendor resolves media by its own origin independent of supplied project. Archive/local-only extensions separate. |
| 13 | POST /images | prompt; model; aspectRatio; count1–4 default4; seed; reference_1..10; character_1..7; email; replyUrl/replyRef; mutually exclusive CAPTCHA controls | Most JSON fields implemented, aliases normalized, weighted refs/fresh budgets. Lite retains conservative transport cap3 pending retained-reference proof, rather than vendor blanket10. Provider retry/order returns501; supplied token supported. Native output uses safe download artifacts rather than vendor raw media/request/signedURL envelope. |
| 14 | POST /images/upscale | mediaGenerationId; resolution2k/4k default2k; CAPTCHA controls | 2k/4k and exact image aliases implemented. CAPTCHA fields rejected by route allowlist. Native/UI upscale remains separate from scope-supported generation token operations. |
| 15 | POST /videos | prompt; model; aspectRatio; duration; resolution; count; seed; email; start/end; image1..7; char1..7; audio1..5; video1; trim indices; async/callbacks/CAPTCHA | Native R2V/edit support reference families and canonical order. General T2V/I2V/Veo-image-only path rejects seed and CAPTCHA fields, rejects landscape/portrait aliases, rejects explicit720p on Veo, supports only16:9/9:16. Native account model capacities are checked; do not infer square/other modes from vendor alone. |
| 16 | POST /videos/upscale | mediaGenerationId; resolution720p/1080p/4K default1080p; async/callbacks/CAPTCHA | Default operation is existing export; real native promotion requires operation=promotion. Promotion supports tier-proven targets/token; repeat cached vendor response and automatic default promotion absent. Explicit export never claims new Google media. |
| 17 | POST /videos/gif | mediaGenerationId | Credit-free export with encodedGif and download artifact; async/callback extensions. Timeout follows durable wait policy instead of fixed vendor90s. |
| 18 | POST /videos/extend | mediaGenerationId,prompt; model defaultfast,count1–4,seed,async/callbacks/CAPTCHA | Native selected-model/ownership extension implemented; aliases supported. Provider replacement retry/order returns501; lower-priority entitlement must be freshly available. |
| 19 | POST /videos/concatenate | media2–10 ordered clips, trimStart/trimEnd0–10 | Local ffmpeg concatenation with duration/aspect checks; managed MP4 registry only. Registered native aliases are not normalized/downloaded. Output includes local artifact and base64 only≤20MiB, not Google's raw export DTO; no inputsCount field. |
| 20 | POST /voices | email,preset,displayName1–200,dialog/performance1–120,CAPTCHA | Saved TTS creation implemented and scoped token supported. async/callback extensions; user voice returned as native audio UUID, not automatically synthesized vendor alias. Google accepted voice generation remains separate evidence. |
| 21 | GET /voices | required email; source system/user optional, omission means both | Baseline defaults bundled system-only. Explicit fresh system Google and saved-user paths exist, selected-project scope. Combined default missing; optional source timestamp absent from public saved_voice_item projection. |
| 22 | GET /voices/{ref} | known preset or user composite | Case-insensitive preset and exact registered user alias detail supported; raw saved UUID requires source=user and account/project. Fresh playback URL/no-store. Vendor alias is never guessed. |
| 23 | DELETE /voices/{ref} | user composite | Native saved voice deletion accepts raw UUID plus account/project. Registered resource alias not normalized here. System voice deletion refused. |
| 24 | POST /characters | displayName1–200,imageReference_1,optional2,personalityNotes≤2000,voice preset/user | Native create supports exact managed UUID image inputs, same project, optional voice. Composite image/user-voice inputs absent in this route; native unregistered owned image cannot be used without managed bytes. Response is native UUID/ref, not vendor synthetic identity. |
| 25 | GET /characters | required email | Fresh Google selected-project catalog by default. Account-wide catalog traversal available through project listing, not this list route. Preview URLs intentionally omitted. Optional source create/update timestamps and full joined voice metadata are not all mirrored. |
| 26 | GET /characters/{ref} | character composite | Exact registered alias or raw entity+account/project detail resolves fresh images/thumbnail/voice; no-store. Does not mark absent incomplete voice catalog as deleted. Vendor orphan proof requires positive deletion evidence. |
| 27 | DELETE /characters/{ref} | character composite | Raw entity UUID plus account/project mutation only; exact registered alias normalization missing. Attached voice remains separate lifecycle. |
| 28 | GET /jobs | options summary(default)/executing/history | All explicit statistics modes implemented, SQL aggregates no100-row cap,15-minute counters,top10/type. Baseline omitted options returns durable paginated jobs instead of summary. Scheduler uses queue load, not these scores or vendor quarantine. |
| 29 | GET /jobs/{jobId} | jobId | Durable status, request, safe response/error and uncertain recovery handles. Vendor encoded ID/auth-domain/410 expiry lifecycle absent; local bearer owns instance. Result field projection intentionally excludes private raw worker fields and signed URLs. |

## Baseline cross-cutting contract differences

- JSON generation handlers do not implement multipart/form-data alternatives. Unknown fields normally produce422 with FastAPI detail, while official examples commonly use400/error.
- Async201 and synchronous completion/error/wait408 exist. Wait408 explicitly reports processingContinues and forbids blind replay; it is not evidence that Google abandoned work.
- Callback event payload is the same durable job record as polling. Existing callbacks validate allowlisted public HTTPS endpoints, retry delivery up to5 times and use10-second HTTP timeout; official image callbacks specify5seconds.
- Account selection uses queued/running load. Official last15-minute score and reason/model quarantine (including explicit-email bypass and single-account exception) are absent. These are scheduling features, not prerequisites to emit the statistics already measured.
- Provider retry loops remain an explicit501 until accepted replacement-token evidence. Retrying an acknowledged or outcome-unknown Google mutation must never be added as generic transport retry.
- Vendor cookie/session secrets, global CAPTCHA statistics and free CAPTCHA credits should not be fabricated to resemble the hosted service.

## Historical next deliveries from the baseline

1. Default GET/jobs to summary, preserve explicit durable-list extension; add no-options/every-options/filter-conflict regression tests. No Google required.
2. Default selected-account GET/voices to fresh combined system+user, retain explicit bundled and user modes; two serial source reads, no nested lease. Tests prove sources, account/project, metadata-only output and no user audio URLs in list.
3. Normalize established landscape/portrait aliases and permit explicit Veo720p only if it is the existing wire default. Forward general-video seed/CAPTCHA only after tracing the underlying SDK/CLI transport, not by extending allowlists alone.
4. Exact registered alias translation for character creation/deletion, saved voice deletion and concatenation. Preserve current account/project/type proof; cache images or videos only through source-backed bounded downloads. Do not decode vendor prefixes.
5. WebP upload can transcode validated bytes to existing PNG transport if the public contract explicitly reports this conversion; requires MIME/size/dimension tests.
6. Local timestamped CAPTCHA observations and filters are implementable; global anonymized statistics are outside local scope. Schedule only after successful acceptance/error data exists.

## Focused final verification

Offline contract tests: default/mode selection, all documented canonical fields and aliases, strict booleans/counts, mixed registered scopes, one-use token lifecycle, safe callbacks, no queue on preflight refusal. Root performs representative authenticated reads and only authorized bounded generations. The matrix deliberately does not translate source coverage into a completion percentage.



## Delivery after the audited baseline — 4 October
The table above records the baseline. Subsequent implementation changes:
| Rows | Delivered | Remaining boundary |
|---|---|---|
|7| Timestamped local phase events, date/limit/provider filters, confirmed acceptance rate and matched local latency | Global/tier/SKU/billing statistics unavailable |
|8| WebP validation and explicit PNG conversion | Native transport receives PNG/JPEG |
|12,23,24,27| Exact alias mutation normalization and confirmed-delete receipts | Arbitrary vendor prefixes and unknown already-gone IDs unsupported |
|13| Lite10 admission and separate character pool with actual image weights; live ten-chip/wire capture and one decoded owned output passed | Per-reference visual influence remains unproved |
|13,14,Native video,18,20| Image/native/generic count1-4 provider controls and confirmed-WAF-only bounded retries | Real solver-backed acceptance unverified |
|21| Fresh combined selected-account system/user default | Account-wide completeness unknown |
|28| Default summary, durable-list extension, score-based automatic selection and exact quota/model local cooldowns | Native Google reset time unobserved |
|1,2,3,29| Accepted refresh lineage preserves aliases, statistics, idempotency and exact receipts | Successful live import and automatic renewal unverified |

Read-only inventory synchronization is a fork extension, not fabricated vendor
completeness. Seed/aspect/entitlement and some response fields remain differences.
Text multipart and image-callback5second timing were subsequently implemented;
see the current scope below. All six historical next deliveries above are addressed
within their documented boundaries.


### Next overnight source scope
Generic video count1 now supports configured provider order and explicit1–10 positive-WAF-only attempts across portable SDK/CLI/queued MCP and HTTP; confidential queued MCP tokens refuse. Image2K/4K overrides and explicit HTTP refusal retries are implemented with fresh4K availability-before-mint. Bounded observed account character/saved-voice listing is an additive extension with opaque continuations, unknown completeness and no deletion authority. Exact live ten-reference wire retention passed after the append-caret fix. Release/gate status remains in VERIFICATION.md; these source scopes do not prove accepted solver-backed output.


Text-only multipart requests now share the JSON mutation handlers. See [form requests](FORM_REQUESTS.md) for exact field conversion, duplicate/file refusal and private token lifecycle. Native binary asset uploads retain their separate contract.


Row7 now additionally has measured local solve/acknowledgment latency averages and sample counts. Only matched phases within one observer lifetime contribute; historical/unmatched events remain unmeasured. Billing, vendor-wide samples and unobserved tier/SKU dimensions remain unavailable.

### Third overnight batch
Generic count2–4 now uses one native RPC across SDK/CLI/MCP/private REST worker with all-output checkpointing and provider/supplied-token controls. Numeric seed and unobserved native output forms remain unsupported. Text multipart requests reuse existing JSON mutation validators; local CAPTCHA elapsed averages and exact typed native quota/model routing are implemented. Policy reset times are local compatibility rules, not Google observations. Retired physical profile names and public handles require fresh registration names. See [batches](VIDEO_BATCH.md), [forms](FORM_REQUESTS.md) and [scheduler](ACCOUNT_SCHEDULER.md).


### R02 read-contract continuation — 4 October 2026

Native image/video, character and saved-user-voice read adapters now accept exact
locally registered composite mappings across SDK/CLI/REST/MCP, with explicitly
selected enabled profile/project and fresh ownership/type/workflow proof. The
private mapping must exist on that host; unknown UseAPI prefixes are not decoded.
Generation and mutation contracts retain their previous scope.

Existing generated-video GetMedia responses can omit width/height. Lookup returns
null rather than assuming sizes; bounded MP4/raw downloads measure dimensions
with ffprobe and validate supplied metadata if present. Live existing generated
video retrieval passed720x1280 with no generation. REST user-voice details now
retain optional description from the shared decoder. Saved-user playback and
voice-alias live acceptance remain unavailable: the one additional authorised
preview was explicitly quota/access refused with NativeQuotaError and unchanged
credits. Implemented adapters do not establish live acceptance.


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
