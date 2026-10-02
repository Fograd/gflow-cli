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
| `GFLOW_SELFHOST_SYNC_WAIT_SECONDS` | Default85; range0–85;0 returns accepted jobs immediately |
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
| `GET /accounts`, `/accounts/{handle}` | Read registered profiles and operator-attested health |
| `POST /accounts`, `DELETE /accounts/{handle}` | Register an existing local profile or remove its registration; no cookie import or profile deletion |
| `POST /images` | Text or registered image references; three Nano Banana model aliases, five image aspects, count 1–4 |
| `POST /images/upscale` | Native Google upscale via the fork's CLI, `resolution: "2k"` or `"4k"`; Google enforces plan entitlement |
| `POST /assets`, `/assets/{handle}` | Raw PNG/JPEG/MP4 upload, maximum 20 MiB; synchronous tee-compatible response |
| `GET /assets/{id}`, `/assets/{id}/download` | Metadata and protected bytes for this server's managed assets |
| `GET /assets/projects/{handle}` | Local catalog by default; source=google reads paginated native account projects |
| `GET /assets/media/{handle}` | Managed catalog by default; source=google reads selected-project native timeline |
| `GET /jobs`, `/jobs/{id}` | Durable jobs; list filters email/status/kind plus limit/cursor |
| `DELETE /assets/{handle}` | Native reversible whole-batch archive; explicit localOnly cache deletion is separate |
| `POST/GET /accounts/captcha-providers`, `GET /accounts/captcha-stats` | Private solver configuration/statistics; provider generation guarded with HTTP 501; see CAPTCHA.md |
| `GET /voices`, `/voices/{ref}` | Bundled presets by default; catalog=google reads native system presets; case-insensitive lookup |
| `GET /characters`, `/characters/{ref}` | Native project summaries/detail |
| `PATCH/DELETE /characters/{ref}` | Native metadata changes/removal; inspect unconfirmed outcomes before retry |
| `POST /characters` | Native one/two-image creation with initial notes; voice assignment unsupported |
| `POST /videos` | Text, start/end image or image-ingredient video adapter, explicitly enabled; not verified with paid live generation in this deployment |
| `POST /videos/upscale`, `/videos/gif` | Native export adapter: 1080p or original 720p, 270p GIF; no new generation |
| `POST /videos/concatenate` | Local ffmpeg equivalent on 2–10 managed MP4 clips; same account, same dimensions and valid trims |

Generation, upscale, GIF export and concatenation accept `async` (boolean). The
default `false` waits up to 85 seconds for a terminal result; a longer operation
returns its original durable job. `async: true` returns immediately. Responses use
HTTP **200** with `jobId` and status; poll `/jobs/{jobId}` while status is `created`
or `running`. This differs from useapi explicit-async201 and unbounded synchronous
expectations. Image results contain
`media[].image.generatedImage.encodedImage` for tee decoding.

Raw uploads return HTTP200 with
`mediaGenerationId: { "mediaGenerationId": "Google UUID" }` and `email`.
MP4 uploads accept `X-Flow-Rights-Confirmed: true` or `false` (exact lowercase); absent means false. Only send true when you can confirm rights for this upload. It permits the native worker to accept a Google rights notice for that request; it is not an account preference. A notice without permission produces `upload_rights_required`; confirm in the browser or submit a new request/new idempotency key with true if entitled. The rights boolean participates in idempotency. The header is rejected on image uploads.

References must be IDs issued by this service. The registry retains account,
project and saved bytes. useapi's opaque identifiers cannot be used directly.
Uploaded references are re-uploaded into the pinned generation project as needed.

System voice requests accept only `?source=system` and optional `email`. Custom
voice creation, cloning, deletion and custom voice lookup are not implemented.
The default voice list is the SDK's bundled catalog. Explicit `catalog=google`
reads the live native system preset catalog; custom saved voices remain separate.

Video generation accepts `veo-3.1-fast`, `veo-3.1-quality`, `veo-3.1-lite`,
`veo-3.1-lite-low-priority`, and `omni-flash`, subject to the underlying SDK's
model/duration validation. Counts 1–4 run serial single-output calls with durable output checkpoints; inspect
partial results if a later call fails. Paid live video verification remains pending. Export jobs return protected download paths
for local variants while retaining the source Google media ID. GIF export uses a
job/download path, rather than useapi's synchronous `encodedGif` response.

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

Image requests accept a native integer `seed` with room for `count` consecutive
seeds (`0..2147483647-count+1`); see [seed evidence](SEEDS.md). Image-only supplied-token rewriting and provider configuration are described in [CAPTCHA.md](CAPTCHA.md). `captchaToken` has a one-shot transport override; live replacement acceptance is
unverified. `captchaOrder` and `captchaRetry` return501 before queueing because the
native action remains unmeasured. Provider keys alone do not enable generation.

Still unsupported: automatic image aspect, inline grounding/entity/audio controls,
full character reference/voice creation and generation binding, custom voices, exact useapi deletion/full library sync,
video extension/V2V and video CAPTCHA overrides. Unknown controls return501.

Lists accept `limit` 1–100 and opaque `cursor`; jobs also accept `email`, `status`
and `kind`, managed media accepts `projectId`, and `source=google` for a native selected-project timeline; asset lookup accepts `raw=true`
for protected bytes. Unknown or repeated query keys are rejected. Default catalogs are local. Native timeline rows carry media_id/workflow_id, caption, archived and batch_media_ids plus mediaGenerationId/projectId aliases; they do not claim merged attached-media history or inferred media types.

Account registration accepts `profile`, `email`, `projectId`, `enabled` and
`verified`. Defaults are disabled/LOGIN_REQUIRED. Enabling requires `verified:true`
and an existing local profile; this is operator attestation, not a Google probe.
Removing registration refuses active jobs and keeps the browser profile. Local
asset deletion with `localOnly:true` requires `mediaGenerationIds` (up to 100) or
`projectId`, refuses active references and never changes the Google library. Without localOnly, DELETE requires projectId and 1–100 distinct media UUIDs, queues reversible native archive, and validates the entire selected-project batch before mutation. All siblings in a generation batch must be selected. After successful upload/archive acknowledgement, poll the timeline for visibility; do not retry the mutation merely because a listing is stale. This is not irreversible individual deletion or useapi already-gone idempotence.

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

Non-empty image output counts must match the requested count. A mismatch produces a failed job with `image_output_count_mismatch`, `expectedCount`, `receivedCount` and `retryable:false`; every returned image remains in `media` and its asset record. Inspect those outputs before any new generation. See [the bounded reliability test](STRESS_TEST.md).

Empty or malformed image results fail validation instead of claiming completion.

For a local masked key editor and credit-free balance check, see [the CapSolver GUI guide](CAPSOLVER_GUI.md). Saving a key does not automatically change generation or prove Google token acceptance.

CAPTCHA statistics distinguish typed generation refusal (`rejected`) from post-submit timeout/download failures (`unknown`). `accepted` is recorded after successful download; counters do not cause retries.

Native project discovery: `GET /assets/projects/{handle}?source=google` returns the account project catalog with `projectId`, `name`, optional modification timestamps/last media ID, `cursor` and explicit native scope. Pages have a fixed size of 21; `limit` is rejected. Pass the returned opaque cursor unchanged (maximum 4096 characters), stopping at null. This is direct account project discovery, not useapi media-history totals/byType or oldest/newest aggregation. Poster URLs and session data are omitted. Default `source=local` retains local pagination.


Native read examples (use the bearer client from the example above):

```python
projects = client.get("/assets/projects/account-one", params={"source": "google"})
characters = client.get("/characters", params={"email": "account-one", "source": "google"})
voices = client.get("/voices", params={"email": "account-one", "source": "system", "catalog": "google"})
```

Native character and voice reads accept optional `projectId`, defaulting to the configured project. Character summaries expose `ref`, `projectId`, `displayName`, `workflowIds` and optional `thumbnailMediaId`; they are project-scoped, not account-wide useapi character CRUD. Native detail/metadata patch/delete adapters are implemented below. One/two-image POST creation has native adapter and deployed HTTP lifecycle proof; use in generation is unsupported. Native system voices are fetched dynamically (30 presets observed); default bundled voices remain available. `GET /voices/{ref}` uses the selected catalog. Custom voice creation/clone/delete and user voice listings remain unsupported.


Limited native character operations: POST `/characters` accepts `displayName` (1–200 characters), optional `personalityNotes` (at most 2000 characters) and one `imageReference_1` and optional `imageReference_2`, each a registered PNG/JPEG in the selected project, plus optional account/project controls. The adapter validates both saved PNG/JPEG images, account/project ownership and active native workflows before creating any entity, then creates the character and copies the reference through the measured native binding operation. The copied workflow is distinct from the source and the original stays active. A merely local/raw-upload reference without that native workflow is refused. Initial `personalityNotes` (at most 2000 characters) is supported through a validated metadata update after copying the reference. Two references use the measured portrait slot0/body slot1 convention; both originals remain active. Voice assignment remains unsupported (501).

PATCH `/characters/{ref}` accepts `displayName` and/or `personalityNotes` (at most 2000 characters), with `email`/`projectId` controls. DELETE and GET detail use query account/project controls; when multiple accounts are enabled, detail/mutations require an explicit account. GET detail includes `personalityNotes`, without signed URLs or voice data. These operations are native project extensions rather than exact account-wide useapi semantics.

Character mutations are direct calls with a bounded worker timeout, not durable queued/idempotent jobs. An unconfirmed failure returns HTTP 502: inspect Flow before explicit retry because the mutation may have succeeded. The server does not automatically retry them. Preserve the documented unsupported fields and remaining creation restrictions before treating this as complete character CRUD parity.

If creation succeeds but reference binding or initial metadata update is unconfirmed, HTTP502 can include `createdCharacterRef` and `projectId`. Keep those identifiers and inspect the existing draft; do not blindly repeat creation. The API does not automatically retry or delete the unknown-result character. Native adapter and deployed HTTP one/two-image create/copy/list/update/delete are verified.

Native creation, reference copying, catalog visibility and optional initial metadata update share a 45 second deadline. Deletion and its visibility check also have a 45 second deadline. Timeout never starts a replacement mutation; retain partial identity and inspect Flow.


For the verified one-image character flow, start with a generated image ID registered by this service:

```python
project_id = client.get("/accounts/account-one").json()["projectId"]
# image_id comes from the completed owned image job in that project.
created = client.post("/characters", json={
    "email": "account-one", "projectId": project_id,
    "displayName": "Ceramic mascot", "imageReference_1": image_id,
    "personalityNotes": "Calm and precise",
})
created.raise_for_status()
ref = created.json()["character"]["ref"]
updated = client.patch(f"/characters/{ref}", json={
    "email": "account-one", "projectId": project_id,
    "personalityNotes": "Warm and precise",
})
updated.raise_for_status()
read = client.get(f"/characters/{ref}", params={"email": "account-one", "projectId": project_id})
read.raise_for_status()
# DELETE uses the same explicit account/project query controls when removal is intended.
```

These native operations copy the source image; they do not generate a new portrait. Keep the returned character reference and project, especially after an unconfirmed failure. Character creation/detail/update/removal is verified for one/two-image flows; voice assignment remains unsupported.

For two references, add `imageReference_2` to the create request. Both must belong to the same account/project and pass validation before mutation. Portrait is slot 0 and body is slot 1. Copying both references and applying notes uses the same 45 second post-create deadline, with partial identity preserved on an unconfirmed outcome.

### Automatic image aspect

`aspectRatio:auto` currently returns HTTP501 before job submission: the native automatic-aspect UI/wire contract has not been measured. An [abort-only investigation](../superpowers/spikes/2026-10-02-image-auto-aspect.md) verified an owned reference and explicit square aspect, but its chooser selector failed; that result is inconclusive about native Auto availability. Use an explicit image ratio. The adapter does not silently infer a different ratio.


### Voice assignment evidence boundary

Voice assignment still returns 501 in this adapter. Two guarded empty-dialogue
preset probes did not complete the picker-to-character transition: the selected
button candidate was unverified, the dialog stayed open and blocked the header
commit. This is not evidence that Google lacks voice assignment. No TTS was
generated and both owned test characters were removed. See the
[redacted transition evidence](../superpowers/spikes/2026-10-02-native-voice-picker-transition.md).
