# Moving a tool from useapi to this fork

This fork provides a bearer-protected Google Flow service on your own host. It uses your saved Chrome profiles and Google allowances. It does not require a useapi subscription. Google plan limits remain in force.

Start with [setup and operation](OPERATIONS.md), then compare your requests with [the API guide](API.md) and [the endpoint inventory](PARITY.md). The inventory separates implemented operations, local equivalents, unported native operations and live verification. A route returning501 is an explicit gap, not a successful substitute.

## Tee pipeline

Keep the existing provider selected until an isolated request succeeds against this service. The REST root is `http://HOST:8844/v1/google-flow` on your private network, or `http://127.0.0.1:8844/v1/google-flow` through an SSH tunnel. Use the self-hosted bearer token, not a useapi token.

The existing tee `GoogleFlowClient` has a hardcoded `base_url`. For an isolated verification process, set its `base_url` after construction. For permanent integration, add a provider/base URL setting and restart tee through its usual deployment process. Do not replace production settings just to run a smoke test.

```python
import os
from app.useapi_google_flow import GoogleFlowClient

client = GoogleFlowClient(token=os.environ['GFLOW_DAEMON_TOKEN'])
client.base_url = 'http://127.0.0.1:8844/v1/google-flow'
image = client.generate_image('A blue ceramic mug', model='nano-banana-2',
                              aspect_ratio='1:1')
```

The existing tee polling contract accepts HTTP200 and a `jobId`; completed image jobs include `media[0].image.generatedImage.encodedImage`. This avoids changing tee's Google-only signed URL download allowlist. Raw image upload returns the nested `mediaGenerationId.mediaGenerationId` and selected account handle that tee expects.

Tee's reference-generation code currently stores the uploaded input ID as the returned `GeneratedImage.media_generation_id`. Read the generated result's `media[].mediaGenerationId` instead before upscaling; otherwise the subsequent request may upscale the input rather than the generated design.

## References and account handles

useapi reference strings encode its own user and account registry. They are not raw Google media UUIDs. They cannot be passed to this fork unchanged. Upload the original bytes again, generate new media through this service, or register a verified Google ID with its owning profile/project through a supported native import path. Do not strip parts off an opaque reference and guess.

The configured `email` field may be an operator alias. It identifies one authenticated Chrome profile; it does not sign Google in. All references in one request must belong to that profile. Google accounts have separate projects, limits and sessions.

## Request compatibility

Use [the API guide](API.md) for the current response modes and supported fields. Preserve an `Idempotency-Key` and the identical request body on connection retries. A job may still be running after the caller times out; poll its ID before sending another operation.

Inspect `/capabilities` and authenticated `/openapi.json` against the deployed build. Default project/media catalogues contain local records. Explicit source=google reads the native account project catalog or selected-project timeline, not useapi history-count aggregation or a complete merged media inventory. DELETE without localOnly performs reversible whole-batch archive; migrate destructive useapi callers deliberately around that documented difference. Local concatenations carry local artifact IDs and cannot be sent to native Google generation as Google media references.

Private LAN callbacks are currently rejected. Polling works across that network. Public callbacks require an allowlisted HTTPS hostname. Callback failure never causes generation to run again.

## Cutover and rollback

1. Verify authentication, one text image, one uploaded reference variation and a native2K result. Confirm dimensions, not just a successful response. The completed job exposes the generated output ID.
2. Repeat account-specific verification before enabling a second or third profile. Register only profiles whose login and Flow access were checked.
3. Run your tool's normal request path with the new URL and token. Confirm error handling, polling and account pinning using an isolated job.
4. Change production's provider/base URL only after those checks. Keep the previous URL/token in protected configuration until the first normal workload completes.

Rollback means pointing the consuming tool at its previous provider. Keep the fork's queue and outputs: an interrupted or already accepted job may still have completed on Google. Inspect those jobs before resubmitting them elsewhere. Do not delete saved profiles or queue records as part of rollback.
