# Native video resolution promotion
This operation asks Google to generate a promoted video. It may spend credits. Existing video exports keep their behavior.

## Commands and API
```sh
gflow video upscale-models --project PROJECT_UUID --resolution 720p --profile pro2 --json
gflow video upscale-native VIDEO_UUID --project PROJECT_UUID --resolution 720p --profile pro2 --json
```
Targets:720p,1080p,4k. The default is1080p. Optional model-key must occur in the fresh account inventory. Optional captcha-token-file reads one owned private token file; use the R06 single-use VIDEO_GENERATION rules.
SDK:FlowApiClient.list_native_promotion_models(project_id,resolution=...), upscale_native_video(project_id=...,media_id=...,resolution=...,model_key=...,on_started=...), wait_native_promotion(started,timeout_s=600).
Direct MCP:gflow_list_video_upscale_models(project,resolution,profile); gflow_upscale_native_video(project,media_id,resolution,model_key,profile,out_dir,captcha_token). Both are direct tools; they do not use the queued generation MCP tool.

HTTP:
```json
{"mediaGenerationId":"VIDEO_UUID","operation":"promotion","resolution":"720p","email":"ACCOUNT_HANDLE","projectId":"PROJECT_UUID","async":true}
```
POST /v1/google-flow/videos/upscale; GET /v1/google-flow/videos/upscale/models?email=ACCOUNT_HANDLE&projectId=PROJECT_UUID&resolution=720p. Omit operation for native promotion1080p; set operation=export to retain legacy exports. GIF has no promotion selector.
Promotion accepts optional modelKey,captchaToken,captchaOrder,captchaRetry,replyUrl,replyRef. Configured provider selection and explicit1–10 typed WAF-only retry are implemented; Google acceptance remains unverified. A supplied token is privately persisted outside the durable job payload and consumed once by the private worker.
Unknown fields are refused. Unsupported targets are422. Fresh unavailable model/account/source combinations refuse before token mint or generation.

## Account and source checks
A fresh project snapshot must bind the video to an active owned workflow. A fresh GetMedia response must match all three identities and have an exclusive video arm plus valid dimensions. For an otherwise strictly verified generated/uploaded video
with explicitly absent width and height, promotion reuses R02's protected MP4
read and ffprobe measurement: at most256MiB,90seconds and15seconds for ffprobe,
no redirects/cookies, private temporary copy removed even on failure. Partial or
malformed dimensions refuse. Known dimensions need no source download. Missing
URLs only refuse when measurement is necessary; no dimension/aspect is guessed. No original-file URL is needed to submit promotion.
Inherited landscape16:9 or portrait9:16 must match a fresh tier-available model usage. Promotion tasks21/15/16 correspond to720p/1080p/4k; the target must also occur in the usage resolution list. Three Pro subscriptions do not establish4K entitlement.
Each invocation assigns one output media ID and retains the source workflow, matching Google's UI destination. It checkpoints before one p0UkFb request. Uncertain outcomes retain known handles and never resubmit automatically.
Native numeric promotion seed field4 is observed, but its allowed range is not established; this option is not exposed. Assignment UUID seeds are separate.

## Completion and limits
Polling follows the exact assigned media/workflow. The worker rereads owned output metadata and checks the requested short-side pixels720/1080/2160. Safe download validates the actual video against that metadata. The SDK wait also rereads the exact owned output and validates identities, target
and inherited aspect; an explicitly dimensionless output uses the same bounded
measurement. Workers verify decoded bytes as well as metadata. Results include
output identifiers, local paths, actual width and height; HTTP returns managed download paths, operation native-promotion and resolution. Signed Google URLs are transient.
The private promotion-started.json contains known IDs, not CAPTCHA tokens. If interrupted, inspect those IDs and Flow before another request. Complete restart journal recovery remains R11 work.
Source/codec/preflight evidence proves request construction and account discovery. It does not establish accepted paid promotion, final resolution quality or successful4K output. Those are R12 acceptance work.

CLI `video upscale-native` mirrors REST provider controls with `--captcha-order` and
`--captcha-retry`; direct MCP `gflow_upscale_native_video` uses `captcha_order` and
`captcha_retry`. Omitted controls use the browser once; explicit retry selects providers.
Supplied tokens are exclusive/single use. The existing promotion worker owns the single
bounded exact-WAF retry loop; accepted/unknown work never replays. See
[native provider controls](NATIVE_CAPTCHA.md#saved-voice-and-promotion-clidirect-mcp-provider-controls).


## R07 implementation closure and acceptance boundary

Supported native targets are720p,1080p(default),4k. A measured640x360 source can
prepare720p using task21/enum1;1080p uses task15/enum2 and4k task16/enum3.
Sources must retain exact16:9 or9:16; e.g.1280x2274 is not silently coerced.
The requested target is bound to the durable checkpoint. Source and output
workflow/account/project identities remain exact. Unknown submissions and later
poll/read/download/validation failures retain known handles and never replay.

Fresh nonempty model rows mean available for that observed account tier/target,
subject to source-aspect and explicit model checks. A successfully read, validated
catalog with no matching row means unavailable for that target at that time.
Unreadable/malformed tier/catalog or unverifiable source means unknown, returned
as an explicit preflight error. A plan name or configured account count is no
entitlement proof; available metadata does not prove rendering or remaining quota.
Native model catalogs are synchronous reads; native promotion uses direct MCP
and the existing private REST worker, with no generic queued-MCP codec twin.

5 October zero-generation BDD prepared an owned synthetic640x360-to720p request
using fresh pro2 models (720p:1,1080p:1,4k:0), with real token mint replaced by a
local stub and generation RPCs blocked. Only that fixture was archived and
original active assets were preserved. This is request-preparation evidence.
Existing browser image2K acceptance stands. Implementation complete, paid
acceptance pending: accepted video promotion, solver-backed upscale and entitled
image/video4K outputs require separately authorized R12 credit/solver tests.
The roadmap's full R07 acceptance checkbox remains open.

## R12 export and promotion evidence
Original 720p MP4 and 270p animated GIF exports passed on existing owned clips.
Export captures bounded browser download events as well as page blobs, validates
MP4/GIF signatures and removes listeners/tasks on timeout or cancellation. This
is distinct from native promotion: the R12 1080p native request was explicitly
refused by Google. No native higher-resolution acceptance is claimed.
