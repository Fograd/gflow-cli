# Self-hosted Google Flow API

Run `python -m gflow_cli.selfhost` from the fork's Python environment. The REST
service is separate from the existing MCP service. It is intended for one trusted
operator and their Google accounts. Its default address is `127.0.0.1:8844`.

All routes require `Authorization: Bearer <GFLOW_DAEMON_TOKEN>`. Store the token in
the host's secrets environment file. Never put it in source control or a URL.
Private network access requires an explicit `GFLOW_SELFHOST_HOST` override.
Use TLS or an SSH tunnel across untrusted networks.

## Configuration

| Environment variable | Meaning |
| --- | --- |
| `GFLOW_DAEMON_TOKEN` | Required bearer token, shared with the existing MCP daemon if desired |
| `GFLOW_SELFHOST_ACCOUNTS` | JSON object mapping enabled profile names to `{ "email": "account handle", "project": "Google project UUID" }` |
| `GFLOW_SELFHOST_ROOT` | Private SQLite queue, uploads and output root; default `$GFLOW_CLI_HOME/selfhost` |
| `GFLOW_SELFHOST_HOST` | Listen address; default `127.0.0.1` |
| `GFLOW_SELFHOST_PORT` | Listen port; default `8844` |
| `GFLOW_SELFHOST_CALLBACK_HOSTS` | Comma-separated exact HTTPS hostnames; empty disables callbacks |
| `GFLOW_SELFHOST_ALLOW_VIDEO` | Set `1` to enable generation that spends video credits; default disabled |

Keep existing `GFLOW_CLI_HOME`, `GFLOW_CLI_HEADLESS=false`, and `DISPLAY` settings
from the headed Chrome deployment. Each configured profile must already be logged
in and verified. The account handle can be an operator alias. Add the second and
third accounts only after login and a successful generation. The server does not
infer a usable session from the existence of a Chrome cookies file.

The `health: "OK"` account response means the operator enabled that verified
profile. It is not a fresh Google entitlement or quota check. Each account has one
serial worker. The underlying SDK also retains its cross-process profile lease,
so REST, MCP and CLI calls cannot drive the same Chrome profile simultaneously.

## Routes and current coverage

All routes use the `/v1/google-flow` prefix. See authenticated `GET /capabilities`
for the running adapter's declared scope. `GET /openapi.json` describes its routes.

| Route | Behaviour and limits |
| --- | --- |
| `GET /accounts`, `/accounts/{handle}` | Read configured, enabled profiles |
| `POST /images` | Text or registered image references; three Nano Banana model aliases, five image aspects, count 1–4 |
| `POST /images/upscale` | Native Google upscale via the fork's CLI, `resolution: "2k"` or `"4k"`; Google enforces plan entitlement |
| `POST /assets`, `/assets/{handle}` | Raw PNG/JPEG upload, maximum 20 MiB; synchronous tee-compatible response |
| `GET /assets/{id}`, `/assets/{id}/download` | Metadata and protected bytes for this server's managed assets |
| `GET /assets/projects/{handle}` | Local gflow project catalog, labelled as such |
| `GET /assets/media/{handle}` | This server's managed asset catalog |
| `GET /jobs`, `/jobs/{id}` | Durable accepted jobs and terminal results |
| `GET /voices`, `/voices/{ref}` | Bundled system voice names, descriptors and sample URLs; case-insensitive lookup |
| `POST /videos` | Single text-to-video adapter, explicitly enabled; not verified with paid live generation in this deployment |
| `POST /videos/upscale`, `/videos/gif` | Native export adapter: 1080p or original 720p, 270p GIF; no new generation |
| `POST /videos/concatenate` | Local ffmpeg equivalent on 2–10 managed MP4 clips; same account, same dimensions and valid trims |

Generation, upscale and concatenation return HTTP **200** with `jobId` and
`status: "created"`. Poll `/jobs/{jobId}`. Completed image jobs carry
`media[].image.generatedImage.encodedImage` as base64 bytes, which the tee client
can already decode. This intentionally supports tee's accepted-job polling
contract; it does not reproduce useapi's synchronous default for every caller.

Raw uploads return HTTP200 with
`mediaGenerationId: { "mediaGenerationId": "Google UUID" }` and `email`.
References must be IDs issued by this service. The registry retains account,
project and saved bytes. useapi's opaque identifiers cannot be used directly.
Uploaded references are re-uploaded into the pinned generation project as needed.

System voice requests accept only `?source=system` and optional `email`. Custom
voice creation, cloning, deletion and custom voice lookup are not implemented.
The voice list is the SDK's bundled catalog, not a fresh live Google query.

Video generation accepts `veo-3.1-fast`, `veo-3.1-quality`, `veo-3.1-lite`,
`veo-3.1-lite-low-priority`, and `omni-flash`, subject to the underlying SDK's
model/duration validation. Only one output is currently exposed. Multi-output
requests are rejected before billing. Export jobs return protected download paths
for local variants while retaining the source Google media ID. GIF export uses a
queued download, rather than useapi's synchronous `encodedGif` response.

Concatenation accepts `media` items with `mediaGenerationId`, optional `trimStart`
and `trimEnd` in seconds. Each trim is finite and within 0–10 seconds. Combined
trims must leave content in each clip. The local backend produces H.264/AAC at
30 fps and adds silence to clips without audio. Its result identifies
`backend: "local-ffmpeg"` and a new **local artifact ID**, not a Google media ID.
It returns `encodedVideo` up to 20 MiB and a protected `downloadPath` for larger
outputs. The Google library is not modified by concatenation.

## Requests

```python
import base64
import os
import time
import uuid
import httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8844/v1/google-flow",
    headers={"Authorization": f"Bearer {os.environ['GFLOW_DAEMON_TOKEN']}"},
    timeout=90,
)
response = client.post(
    "/images",
    headers={"Idempotency-Key": str(uuid.uuid4())},
    json={"prompt": "A ceramic blue mug on a plain background",
          "model": "nano-banana-2", "aspectRatio": "1:1", "count": 1},
)
response.raise_for_status()
job = response.json()
while job["status"] in ("created", "running"):
    time.sleep(2)
    response = client.get(f"/jobs/{job['jobId']}")
    response.raise_for_status()
    job = response.json()
if job["status"] != "completed":
    raise RuntimeError(job.get("error", job["status"]))
image_bytes = base64.b64decode(job["media"][0]["image"]["generatedImage"]["encodedImage"])
image_id = job["media"][0]["mediaGenerationId"]
upscale = client.post("/images/upscale", json={"mediaGenerationId": image_id,
                                              "resolution": "2k"})
upscale.raise_for_status()
# Poll this job with the same loop before decoding the native upscale bytes.
```

Use a fresh `Idempotency-Key` per intended operation and keep the same key and
body when retrying a failed HTTP connection. A repeated key reuses the original
job and selected account. Reusing a key for a different request returns409.
The queue has at most 100 accepted/running jobs; a full queue returns429.

## Failure and restart behaviour

`created` and `running` jobs are durable. If the daemon stops during execution,
the next start changes that job to `interrupted`, with
`submission_outcome_unknown`. It **never automatically submits that generation
again**. Inspect the Google project and saved outputs before explicitly retrying.
The SDK may have submitted successfully before a browser or download failed.
CLI failures therefore do not claim a precise quota or CAPTCHA diagnosis that
the adapter has not observed, and their raw output is not returned remotely.

Invalid inputs return422, missing authentication401, missing local assets404,
queue capacity429, and unsupported routes or controls501. JSON bodies are bounded
to64 KiB before parsing, raw uploads to20 MiB. Paths and CLI switches cannot be
supplied through the API. Prompts are passed as positional arguments after `--`,
without a shell.

Unimplemented controls include seed, automatic image aspect, useapi inline slot
markers, CAPTCHA token/provider routing, character CRUD, custom voices, account
mutation, asset deletion, video extension and the remaining video reference/edit
cross-product. Unsupported query options and request keys are rejected, rather
than silently ignored. Google project/media catalogs are not fully synchronised.

## Callbacks

`replyUrl` requires an explicitly allowlisted HTTPS hostname, no credentials,
custom port or fragment. The worker resolves and pins a public address; private
addresses and redirects are rejected. Private LAN tee callbacks are currently
unsupported; use polling on that network.

The SQLite outbox persists `created`, `started` and terminal notifications with
`jobId`, status, timestamps, `replyRef`, and terminal media/error fields. Delivery
is at least once, with up to five attempts. Receivers should deduplicate using job
ID and status. Generation is never retried because a callback failed.

## Verification and design record

Preimplementation review: CAUTION. Architect: isolate REST from transport.
Security: require bearer auth, bounded bodies, contained output files and pinned
callbacks. Performance: one worker per profile and one daemon per queue.
CLI/MCP UX: keep existing entry points intact; expose truthful capabilities.
Scope: reuse existing SDK/CLI operations and label local equivalents explicitly.

The test-first plan was: create failure/queue/security fixtures; implement durable
state and process boundary; wire validated endpoints; then run adapter checks and
live image/upload/upscale verification. Critical scenarios include crash after
submission, a retry selecting another account, mismatched reference ownership,
oversized chunked JSON, malformed fields, literal inline markers, hostile callback
URLs, and derived video export replacing its source asset. Offline tests cover
these cases. The deployment's live image, native2K, upload and reference tests are
recorded separately; paid video generation has not been exercised here.

Run focused checks before deployment:

```bash
uv run ruff check src/gflow_cli/selfhost tests/selfhost
uv run ruff format --check src/gflow_cli/selfhost tests/selfhost
uv run pyright src/gflow_cli/selfhost
uv run python -m pytest -q tests/selfhost
```
