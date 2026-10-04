# Native video resolution promotion
This operation asks Google to generate a promoted video. It may spend credits. Existing video exports keep their behavior.

## Commands and API
```sh
gflow video upscale-models --project PROJECT_UUID --resolution 720p --profile pro1 --json
gflow video upscale-native VIDEO_UUID --project PROJECT_UUID --resolution 720p --profile pro1 --json
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
A fresh project snapshot must bind the video to an active owned workflow. A fresh GetMedia response must match all three identities and have an exclusive video arm plus valid dimensions. No original-file URL is needed to submit promotion.
Inherited landscape16:9 or portrait9:16 must match a fresh tier-available model usage. Promotion tasks21/15/16 correspond to720p/1080p/4k; the target must also occur in the usage resolution list. Three Pro subscriptions do not establish4K entitlement.
Each invocation assigns one output media ID and retains the source workflow, matching Google's UI destination. It checkpoints before one p0UkFb request. Uncertain outcomes retain known handles and never resubmit automatically.
Native numeric promotion seed field4 is observed, but its allowed range is not established; this option is not exposed. Assignment UUID seeds are separate.

## Completion and limits
Polling follows the exact assigned media/workflow. The worker rereads owned output metadata and checks the requested short-side pixels720/1080/2160. Safe download validates the actual video against that metadata. Results include output identifiers, local paths, width and height; HTTP returns managed download paths, operation native-promotion and resolution. Signed Google URLs are transient.
The private promotion-started.json contains known IDs, not CAPTCHA tokens. If interrupted, inspect those IDs and Flow before another request. Complete restart journal recovery remains R11 work.
Source/codec/preflight evidence proves request construction and account discovery. It does not establish accepted paid promotion, final resolution quality or successful4K output. Those are R12 acceptance work.
