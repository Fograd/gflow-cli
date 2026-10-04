# HTTP job responses and safe retries

The self-hosted adapter follows the documented [video sync/async responses](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos) and [job record shape](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs-jobid). A durable local job can exist before Google accepts a generation. The adapter does not invent Google operation handles or signed URLs.

## Submit and poll

By default, a generation request waits for completion. A completed sync request returns **200** with `jobId` and its result, including `media` where applicable. Failed requests return an error HTTP status rather than 200.

Set `"async": true` for an immediate **201 Created** response. The response supplies `Location: /v1/google-flow/jobs/<id>`, `jobid`, and the existing camelcase `jobId` alias. Async video generation and video upscale follow useapi's advertised contract. Async image generation, image upscale, GIF, concatenation and library archive are self-hosted extensions; upstream does not advertise that mode for these endpoints.

```python
import requests

headers = {"Authorization": "Bearer YOUR_LOCAL_TOKEN", "Idempotency-Key": "your-unique-request"}
base = "http://YOUR_PRIVATE_HOST:8844/v1/google-flow"
response = requests.post(base + "/videos", headers=headers,
                         json={"prompt": "Your prompt", "async": True}, timeout=30)
response.raise_for_status()
job_id = response.json()["jobid"]
job = requests.get(base + "/jobs/" + job_id, headers=headers, timeout=30).json()
# Poll until status is completed or failed. completed outputs are in response.media.
```

Polling and webhook snapshots have the same public shape:

```json
{
  "jobid": "a-durable-local-uuid",
  "jobId": "a-durable-local-uuid",
  "type": "video",
  "status": "started",
  "created": "2026-10-03T00:00:00.000Z",
  "updated": "2026-10-03T00:00:01.000Z",
  "request": {"prompt": "Your prompt", "async": true}
}
```

`status` is `created`, `started`, `completed`, or `failed`. Terminal results appear under `response`; large media bytes appear only under `response.media`, rather than being duplicated at the top level. Numeric `createdAt`/`updatedAt`, `jobId` and small recovery counters remain compatibility extensions. Internal queue execution states remain separate from this projection. Legacy queued records can omit request mode if it was never recorded.

The request projection excludes supplied CAPTCHA tokens, secret-file locations, input/ref paths, and private worker controls. Results exclude raw worker output, unknown fields, absolute local paths, and signed URLs. Managed download paths remain bearer-protected.

## Wait expiry and unknown outcomes

`GFLOW_SELFHOST_SYNC_WAIT_SECONDS` defaults to **600**, accepts finite values from **0 to 900**, and can shorten the wait. Generation and upscale waits are capped at 600 seconds; local concatenation at 180. Setting it to zero makes a sync request expire immediately with 408; use explicit async mode for an accepted job response.

An unfinished sync wait returns **408**, `jobId`, `processingContinues: true`, `retryable: false`, and a polling `Location`. This deadline stops waiting for an HTTP response; it does not cancel, restart, or replay the durable job. Poll that exact ID before submitting another request. A client disconnect also leaves the durable job tracked.

After a worker timeout or restart during execution, the public job becomes `failed` with `outcomeUnknown: true` and `retryable: false`. This means Google may have accepted the submission. Known output identities, completed files and safe recovery metadata remain available. Inspect the job and Flow before deciding on another submission. An unknown outcome is distinct from a known rejection.

Typed CLI failures map to safe statuses: WAF/access or unavailable upscale **403**, insufficient credits **402**, throttling **429**, reference not found **404**, transport polling timeout **408**, and expired/missing Flow session **596**. The local API's bearer authentication still uses **401**. Unknown command/result failures use **502**. This mapping does not infer missing Google rejection details or claim exact upstream error reasons. Existing request validation uses **422**; unsupported functionality uses **501**.

## Idempotency and callbacks

Reuse the same `Idempotency-Key` for a retry of the same semantic request. Changing only async/sync response mode reuses the existing job; it does not regenerate. The stored request metadata describes the first accepted submission. Changed generation inputs with the same key return 409. This is an extension for preventing accidental duplicate billing, not a promise that Google itself supports idempotency.

`replyRef` must be a string of at most 4,096 characters. It is retained in the public request and top-level callback metadata. `replyUrl` requires an explicitly allowed public HTTPS host. Callbacks use the same safe job projector as polling, persisted transactionally at `created`, `started`, and terminal transitions. They are snapshots at their transition times, rather than rewrites to the newest state. Pending legacy outbox records are safely reprojected without changing the original event state.

Image callbacks use the upstream five-second HTTP timeout; other callback types use ten seconds. Delivery makes up to five attempts with an exact host allowlist, pinned public DNS, Host/SNI and no redirects. Recipient response bodies are never read. Callback retries do not repeat generation. See [image recovery](IMAGE_RECOVERY.md) for journal and partial-download details.

## Image Auto policy

For image-to-image requests, explicit `aspectRatio: "auto"` resolves locally from the first actual supplied reference image in numeric slot order. Nano Banana 2/Pro I2I default to this policy; Nano Banana 2 Lite defaults to 16:9. Text-only Auto and character-only Auto are invalid.

The resolver chooses the nearest of Google's five supported ratios using symmetric logarithmic distance. It decodes a verified managed PNG/JPEG, bounded to 20 MiB and 25 megapixels, after account/project/path checks. This is a documented local approximation, not a claim to reproduce Google's or useapi's unspecified internal sizing algorithm. The transport receives an explicit supported ratio; no native Auto enum is invented.

Job metadata and terminal results report `requestedAspectRatio: "auto"`, `resolvedAspectRatio`, and `aspectPolicy: "derived-first-reference-nearest-supported-v1"`. The public request retains the caller's Auto intent. Multiple reference images always use the first numeric slot for the local resolution; this cannot reproduce upstream mixed-orientation behavior. Use an explicit ratio when exact output orientation matters.
