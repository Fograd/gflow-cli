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
| `GFLOW_SELFHOST_ROOT` | Private SQLite queue, uploads, output and native CAPTCHA observations; default `$GFLOW_CLI_HOME/selfhost`. Use the same explicit root for SDK/CLI/MCP and REST processes |
| `GFLOW_SELFHOST_HOST` | Listen address; default `127.0.0.1` |
| `GFLOW_SELFHOST_PORT` | Listen port; default `8844` |
| `GFLOW_SELFHOST_CALLBACK_HOSTS` | Comma-separated exact HTTPS hostnames; empty disables callbacks |
| `GFLOW_SELFHOST_SYNC_WAIT_SECONDS` | Default 600; range 0–900; per-route ceiling 600 seconds (concatenation 180); zero returns HTTP 408 immediately while processing continues |
| `GFLOW_SELFHOST_IDLE_SESSION_INTERVAL_SECONDS` | Default 0 (disabled); finite seconds >=1800 when enabled; queues bounded idle project-access health reads. This is not authentication renewal. |
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
| `GET /accounts`, `/accounts/{handle}` | Read registered profiles, attested health and separate safe `idleSessionMaintenance` schedule/observation metadata |
| `POST /accounts`, `DELETE /accounts/{handle}` | Register an existing operator-attested profile or import a bounded private cookie table into a staged new/refresh profile after actual identity and project-access checks; deletion removes registration only |
| `POST /accounts/{handle}/health` | On-demand native project-access check through the serial queue; supports async and callbacks; preserves the saved profile and does not refresh login. See [session health](SESSION_HEALTH.md). |
| `POST /images` | Text or registered image references; three Nano Banana model aliases, five image aspects, count 1–4 |
| `POST /images/upscale` | Native Google upscale via the fork's CLI, `resolution: "2k"` or `"4k"`; Google enforces plan entitlement |
| `POST /assets`, `/assets/{handle}` | Raw PNG/JPEG/WebP/MP4 upload, maximum 20 MiB; synchronous tee-compatible response |
| `GET /assets/{id}`, `/assets/{id}/download` | Managed metadata/bytes by default; source=google fresh owned image/video URLs and validated image/video raw |
| `GET /assets/projects/{handle}` | Generated history summaries by default; source=google native catalog, source=local managed cache |
| `GET /assets/media/{handle}` | Native timeline/attached media by default; source=local managed cache |
| `GET /assets/resources/{handle}` | Fork extension: bounded observed account characters/saved voices, opaque continuation, unknown completeness |
| `GET /jobs`, `/jobs/{id}` | Default summary; source=local durable list with email/status/kind/limit/cursor |
| `DELETE /assets/{handle}` | Native reversible whole-batch archive by default; operation=delete permanently removes only selected owned media IDs; explicit localOnly cache deletion is separate |
| `POST/GET /accounts/captcha-providers`, `GET /accounts/captcha-stats` | Private solver configuration/statistics; image/native provider controls supported; see CAPTCHA.md |
| `GET /voices`, `/voices/{ref}` | Fresh combined system/selected-project user voices with email; explicit source=system/user; bundled catalog remains an extension |
| `POST /voices`, `DELETE /voices/{ref}` | One TTS preview plus two metadata saves; permanent saved voice deletion; durable jobs; see [saved voices](VOICES.md) |
| `GET /characters`, `/characters/{ref}` | Native project summaries/detail |
| `PATCH/DELETE /characters/{ref}` | Native metadata changes/removal; inspect unconfirmed outcomes before retry |
| `POST /characters` | Native one/two-image creation with initial notes and system preset or owned saved TTS voice assignment |
| `POST /videos` | Text, start/end image or image-ingredient video; referenceVideo_1 selects native Omni editing with frame trims, up to5 image/3 saved-audio references; ordinary Omni image/audio ingredients use the dedicated native adapter; explicitly enabled |
| `POST /videos/extend` | Native standalone continuation outputs, count1–4; optional modelKey discovered by account tier/source aspect; see [extension](NATIVE_VIDEO_EXTENSION.md) |
| `GET /videos/extend/models`, `/videos/edit/models`, `/videos/reference/models` | Fresh native model keys and credit costs for the selected account/project |
| `POST /videos/upscale`, `/videos/gif` | Default native1080p promotion, optional720p/4k subject to entitlement; explicit operation=export retains legacy exports. GIF is270p export. Paid promotion acceptance remains pending. |
| `POST /videos/concatenate` | Local ffmpeg on 2–10 managed/native owned videos; fresh native validation/cache, same account/project/dimensions, trims and inputsCount |

Generation, upscale, GIF export and concatenation accept async (boolean).
Explicit async returns HTTP 201 with the durable job identity immediately.
The default false waits for completion, up to 600 seconds for generation/export
or 180 seconds for concatenation, bounded by the operator's configured wait.
An unfinished request returns HTTP 408 with jobId and processingContinues; the
worker continues and must not be resubmitted. Poll /jobs/{jobId}: public statuses
are created, started, completed and failed. Interrupted work is failed with
outcomeUnknown and retryable false. GET and callbacks share the same projection;
outputs live under response.media. Completed synchronous image responses retain
media[].image.generatedImage.encodedImage. Image/export/concat async support is a
documented self-hosted extension where useapi does not advertise it. Read
[HTTP job semantics](HTTP_JOB_SEMANTICS.md) for exact response and failure shapes.

Raw uploads return HTTP200 with
`mediaGenerationId: { "mediaGenerationId": "Google UUID" }` and `email`.
MP4 uploads require the exact lowercase header `X-Flow-Rights-Confirmed: true` for every request; absent, false or malformed values fail 422 before queue creation. Only send true when you can confirm rights for this upload. The assertion is per request, never an account preference, and participates in idempotency. The header is rejected on image uploads. This strict consent requirement is a deliberate fork difference from the earlier conditional-notice behavior.

References must be IDs issued by this service. The registry retains account,
project and saved bytes. useapi's opaque identifiers cannot be used directly.
Uploaded references are re-uploaded into the pinned generation project as needed.

System voices use `source=system`; the email-selected default is a fresh combined catalog and
`catalog=google` reads native presets. Project-scoped saved preset-based TTS uses
`source=user` for list/detail/delete and POST `/voices` for creation. These new
adapters await final E2E verification. Voice cloning is unsupported. Read
[saved voices](VOICES.md) for exact limits and the bare-UUID reference contract.

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
          "model": "nano-banana-2", "aspectRatio": "1:1", "count": 1, "async": True},
)
response.raise_for_status()
job = response.json()
while job["status"] in ("created", "started"):
    time.sleep(2)
    response = client.get(f"/jobs/{job['jobId']}")
    response.raise_for_status()
    job = response.json()
if job["status"] != "completed":
    raise RuntimeError(job.get("error", job["status"]))
result = job.get("response", job)
image_bytes = base64.b64decode(result["media"][0]["image"]["generatedImage"]["encodedImage"])
image_id = result["media"][0]["mediaGenerationId"]
upscale = client.post("/images/upscale", json={"mediaGenerationId": image_id,
                                              "resolution": "2k", "async": True})
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

Exact typed WAF and content-policy refusals from generic image, upscale and video
workers retain safe public reasons. Unknown or malformed worker envelopes remain
conservative generic failures; private CLI output is never projected.

Image requests accept a native integer `seed` with room for `count` consecutive
seeds (`0..2147483647-count+1`); see [seed evidence](SEEDS.md). Image supplied-token and provider controls are described in [CAPTCHA.md](CAPTCHA.md).
captchaToken is one use. Configured captchaOrder and explicit captchaRetry1–10
are supported with fresh project/action/site-key proof and typed WAF-only retry;
ambiguous or accepted writes never replay. External-token acceptance is unverified.

Image Auto aspect uses a labelled first-reference approximation across REST, CLI,
MCP and reference batch manifests. Saved TTS lifecycle, saved-voice character binding,
individual permanent media deletion, native standalone extension and Omni editing
are implemented from the deployed frontend codecs. A later native metadata read
confirmed removal of one owned synthetic clip after delayed visibility; the final owned synthetic lifecycle subsequently passed in 28.91 seconds, with all originally active media preserved. The first saved TTS attempt was ambiguous with no acknowledged handles. After correcting its proven preset-case divergence, one captured no0P6 request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7). No audio or saved-voice binding lifecycle was accepted. One native R2V browser-token
attempt was explicitly rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY. Extension,
editing and saved-voice binding acceptance remain pending. Canonical video positional transport and bounded resumable inventory sync are implemented. Numerical generation seeds and authoritative global inventory completeness remain unsupported. Generic count1-4 CAPTCHA controls and all-output tracking are implemented. Unknown controls return501.

`POST /voices` accepts `voice` (case-sensitive canonical preset), `displayName`,
`dialog` and `voicePerformance`. Dialogue/performance each require1–120 characters;
name requires1–200. Account/project and async/callback controls match other jobs.
The fork extension `performance` is an alternative spelling; supplying both
spellings is rejected. Saved voices use bare native media UUIDs, rather than
useapi composite voice IDs. Responses identify `voice`, `mediaId`, `workflowId`
and `source: "user"`; preset metadata is returned only when known.

Omni editing accepts `referenceVideo_1`, `model: "omni-flash"`, an explicit
native `modelKey`, `startFrameIndex_1` (default0), and optional
`endFrameIndex_1`. Frames use the virtual24fps contract with start0–239,
end1–240 and end greater than start. When omitted, end is derived from the measured
owned source duration, rounded down to virtual24fps and capped at240. Missing or
invalid duration fails before token mint/submission. Explicit end remains unchanged. Input references are existing selected-project
media UUIDs: `referenceImage_1..5` and `referenceAudio_1..3`. Audio currently
accepts active owned native audio media UUIDs, including uploaded audio without saved-TTS visibility. Characters use `character_1..7`, or mixed character/image UUIDs in `referenceImage_1..5`; canonical marker indices survive classification. Actual native combined reference capacities apply. Available system presets are also accepted, with fresh native catalog proof and actual audio capacities. Count
is1 and aspect follows the source. The SDK performs fresh native ownership checks.
Results retain resolved `startFrameIndex` and `endFrameIndex`;
`sourceDurationSeconds` is present when measured for an omitted end. These fields
survive synchronous response, job polling and callbacks. Read [video editing](../VIDEO_EDIT.md)
for CLI/MCP and SDK equivalents.

Lists accept `limit` 1–100 and opaque `cursor`; jobs also accept `email`, `status`
and `kind`, managed media accepts `projectId`, and `source=google` for native timeline and attached-media inventory; asset lookup accepts `raw=true`; source=google native lookup also accepts email/projectId and requires explicit account selection
for protected bytes. Unknown or repeated query keys are rejected. Default catalogs are local. Native timeline rows carry media_id/workflow_id, caption, archived and batch_media_ids plus mediaGenerationId/projectId aliases; they do not claim merged attached-media history or inferred media types.

Account registration accepts `profile`, `email`, `projectId`, `enabled` and
`verified`. Defaults are disabled/LOGIN_REQUIRED. Enabling requires `verified:true`
and an existing local profile; this is operator attestation, not a Google probe.
Removing registration refuses active jobs and keeps the browser profile. Local
asset deletion with `localOnly:true` requires `mediaGenerationIds` (up to 100) or
`projectId`, refuses active references and never changes the Google library. Without localOnly, DELETE accepts an optional projectId (defaulting to the selected account's registered project) and requires 1–100 distinct media UUIDs, queues reversible native archive, and validates the entire selected-project batch before mutation. All siblings in a generation batch must be selected. After successful upload/archive acknowledgement, poll the timeline for visibility; do not retry the mutation merely because a listing is stale. Explicit `operation:"delete"` selects permanent individual deletion after fresh
ownership checks and preserves unselected siblings. Receipt-backed retries accept IDs already deleted by this fork after fresh account/project and exact NOT_FOUND checks, without another mutation. Arbitrary absent UUIDs refuse. The free synthetic deletion/retry lifecycle is verified; see [confirmed retries](NATIVE_MEDIA.md#confirmed-deletion-retries-r09). Explicit invalid projectId values refuse rather than selecting a default.

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

Native project discovery: `GET /assets/projects/{handle}?source=google` returns the account project catalog with `projectId`, `name`, optional modification timestamps/last media ID, `cursor` and explicit native scope. Pages have a fixed size of 21; `limit` is rejected. Pass the returned opaque cursor unchanged (maximum 4096 characters), stopping at null. This is direct account project discovery, not useapi media-history totals/byType or oldest/newest aggregation. Poster URLs and session data are omitted. Explicit `source=local` retains local pagination; the HTTP project default is now history.


Native read examples (use the bearer client from the example above):

```python
projects = client.get("/assets/projects/account-one", params={"source": "google"})
characters = client.get("/characters", params={"email": "account-one", "source": "google"})
voices = client.get("/voices", params={"email": "account-one", "source": "system", "catalog": "google"})
```

Native character and voice reads accept optional `projectId`, defaulting to the configured project. Character summaries expose `ref`, `projectId`, `displayName`, `workflowIds` and optional `thumbnailMediaId`; they are project-scoped, not account-wide useapi character CRUD. Native detail/metadata patch/delete adapters are implemented below. One/two-image POST creation has native adapter and deployed HTTP lifecycle proof; Canonical SDK image grounding has one accepted native proof. CLI/MCP/HTTP image acceptance remains pending after safe picker refusals; video grounding remains a gap. Native system voices are fetched dynamically (30 presets observed); explicit bundled voices remain available. `GET /voices/{ref}` uses the selected catalog. Saved preset-based TTS creation, project-scoped user listing/detail/deletion and
character binding are implemented and await final E2E. Cloning remains unsupported.


Limited native character operations: POST `/characters` accepts `displayName` (1–200 characters), optional `personalityNotes` (at most 2000 characters) and one `imageReference_1` and optional `imageReference_2`, each a registered PNG/JPEG in the selected project, plus optional account/project controls. The adapter validates both saved PNG/JPEG images, account/project ownership and active native workflows before creating any entity, then creates the character and copies the reference through the measured native binding operation. The copied workflow is distinct from the source and the original stays active. A merely local/raw-upload reference without that native workflow is refused. Initial `personalityNotes` (at most 2000 characters) is supported through a validated metadata update after copying the reference. Two references use the measured portrait slot0/body slot1 convention; both originals remain active. Optional voice accepts a case-insensitive system preset or an owned saved-TTS
UUID. Saved references require fresh selected-project ownership proof. Preset
metadata assignment is verified; saved binding and rendered speech await final E2E.

PATCH `/characters/{ref}` accepts `displayName`, `personalityNotes` (at most 2000 characters) and/or system preset or owned saved-TTS `voice`, with `email`/`projectId` controls. DELETE and GET detail use query account/project controls; when multiple accounts are enabled, detail/mutations require an explicit account. GET detail includes `personalityNotes`, with optional assigned preset/saved voice metadata and without signed URLs. These operations are native project extensions rather than exact account-wide useapi semantics.

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

These native operations copy the source image; they do not generate a new portrait. Keep the returned character reference and project, especially after an unconfirmed failure. Character creation/detail/update/removal is verified for one/two-image flows; system preset voice assignment is measured. Saved voice CRUD/binding is implemented;
its acceptance and rendered speech await final E2E.

For two references, add `imageReference_2` to the create request. Both must belong to the same account/project and pass validation before mutation. Portrait is slot 0 and body is slot 1. Copying both references and applying notes uses the same 45 second post-create deadline, with partial identity preserved on an unconfirmed outcome.

### Native reference caption identity

Fresh SDK-owned native image references can share a caption on the migrated Flow
host. Captions supply safe picker search text; the selected project's exact media
UUID-to-thumbnail-token match identifies the image. Foreign, inactive, ambiguously
owned or unsearchable references remain refused, and outgoing media IDs remain
guarded. The no-submit live repeated-caption test proves hydration and attachment;
canonical grounding and accepted image output are separate proofs. Unregistered native REST references use explicit configured account/project scope
and fresh ownership; see the ordered reference section below.

### Automatic image aspect

REST managed local-image references support `aspectRatio:auto` through a labeled local policy: derive the nearest supported ratio from the first ordered decoded reference. Nano2/Pro image-to-image defaults use this policy; Lite retains its explicit default. Results preserve requested/resolved aspect and policy metadata. This is an approximation, not an observed native Google Auto sentinel. CLI/MCP and manifest rows now support first-local-reference Auto through the same
policy. CLI/MCP also resolve a first native image UUID from fresh owned selected-project
dimensions; text-only/character-only Auto refuse. REST supports managed assets,
owned native UUIDs and exact registered aliases in ordered slots.
Native Google Auto is not claimed. See [Auto aspect](../AUTO_ASPECT.md).

### Historical voice transition investigation

Earlier guarded empty-dialogue probes did not complete the picker-to-character transition. That historical uncertainty was superseded by the measured native preset assignment and deployed HTTP lifecycle below. This historical metadata proof does not establish rendered speech. The new saved
TTS adapters are documented separately and await final E2E.

### Native system preset assignment

`POST /characters` and `PATCH /characters/{ref}` accept `voice` as a case-insensitive
system preset name, for example `Charon` or `Aoede`. An empty or unknown name is
rejected before mutation. A voice-only PATCH is permitted. Create applies preset
metadata after copying references within the shared mutation deadline; a partial
failure preserves an acknowledged character reference. The native live BDD and deployed HTTP lifecycle
verified Charon on creation, Aoede after update and notes clearing with
preserved preset/two references, with both sources intact.
This is assignment metadata, without a rendered speech or character-generation
binding proof. Custom/user voice CRUD remains unsupported.

For CLI/MCP native project inventory and character mirrors, see the
[surface matrix](SURFACE_MATRIX.md). For preserved outputs after a failed download,
see [image recovery](IMAGE_RECOVERY.md): inspect known native IDs/completed files
before deciding on another generation submission.

Account cookie import is implemented with staged identity/access verification; a
rejected clone was safely refused. A successful live imported-session proof is
pending. Cookies/session values are intentionally never returned. Read the
[cookie import guide](COOKIE_IMPORT.md) for accepted table fields and rollback.

MP4 ingestion now requires X-Flow-Rights-Confirmed: true for every request; missing or false consent fails 422 before queue creation. It is not an account-wide preference. Typed native-media uncertainty preserves bounded known/pending inspection handles and prevents success registration or automatic replay. See [native media operations](NATIVE_MEDIA.md).


## Native image/audio-reference video

`POST /videos` with `model: "omni-flash"` and existing
`referenceImage_1..7` or `referenceAudio_1..5` media UUIDs uses the native
reference-video worker. Audio-only ingredients are supported by the source codec.
The selected available model imposes its own image/audio budgets; the absolute
ceilings do not promise that every tier/model accepts them. Optional `modelKey`
selects an exact discovered key; default selection stays within Omni Flash.
`GET /videos/reference/models?withAudio=true` lists native audio-capable choices.
Aspect choices are16:9,9:16 and1:1. Duration/resolution must match the fresh
native usage. Canonical image/audio markers resolve against the ordered supplied
slots. See [reference video](NATIVE_REFERENCE_VIDEO.md) for SDK/CLI/MCP,
exact source evidence and the pending live-acceptance boundary.

## Final source checkpoint

That historical checkpoint registered 42 tools: the prior 24 plus 18 feature adapters; the current R08 checkpoint registers 43. Native credit inspection and model/catalog reads passed live. This does not prove paid rendering or full vendor parity. A controlled CapSolver Enterprise v3 proxyless VIDEO_GENERATION trial solved one token, submitted once and was rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7); accepted outputs were zero and no retry occurred. Current implementation and these scoped proofs do not establish successful import or generation across all three Google accounts.

Final measured scope: permanent synthetic upload/deletion passed in 28.91 seconds, preserving original active media. Corrected Charon TTS submitted one captured no0P6 request and received PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), with no accepted audio or binding lifecycle. Extension/edit rendering was not additionally billed after the account's refusals; catalog availability is verified separately.

Saved-TTS creation jobs preserve acknowledged ref/mediaId/voice and workflowId
UUIDs, source=user, displayName and bounded voice metadata in synchronous
responses, job polling and callbacks. These identifiers can be supplied to the
saved-voice detail, deletion and character-binding adapters. A native ambiguous
voice/video error instead carries outcomeUnknown=true with validated
knownMediaGenerationIds/knownWorkflowIds for inspection; it remains nonretryable.
A positively identified Google unusual-activity refusal returns403 without
outcomeUnknown. No raw worker diagnostics or credentials are projected.

## Ordered native and managed image references

POST /images can mix managed PNG/JPEG IDs from POST /assets/{email} with
owned native image UUIDs in reference_1 through reference_10, subject to the
selected model's actual reference budget. The slot numbers and prompt marker
order are preserved; a repeated marker attaches its image once.

An unregistered native UUID requires an explicit configured email and the
selected or configured default projectId. The worker checks fresh ownership in
that account/project before uploading managed files or submitting generation.
A managed asset owned by another registered account refuses before queueing.
This does not enable arbitrary remote asset download or account-wide discovery.

For aspectRatio:"auto" (also the reference-image default for nano-banana-2),
the first image reference controls the documented nearest-supported-ratio
approximation. A managed first reference uses its decoded file dimensions.
A native first reference resolves dimensions inside the selected account worker;
missing dimensions fail before generation and never fall back to another input.
requestedAspectRatio, resolvedAspectRatio and aspectPolicy describe the
actual decision. This remains distinct from Google's own native Auto control.

CLI gflow image i2i --reference-syntax slots and MCP
gflow_generate_image(reference_syntax="slots") preserve interleaved local-path
and native-UUID caller order through direct and queued execution. REST managed
IDs are server-owned files; the request does not accept caller filesystem paths.
Names-mode mixed references remain guarded when an explicit ordered slot plan
is required.

Uploads bind only a reply correlated with the current chooser request. The
current typed acknowledgement cross-checks media/project/workflow identities,
the exact upload name and image dimensions. Earlier acknowledged upload IDs are
retained if a later upload or prompt binding fails. Inspect those returned
recovery handles before resubmission; no upload is automatically replayed.
Accepted mixed/native REST and MCP output remains part of final E2E verification.

## Native project media inventory

GET /assets/media/{handle}?source=google merges observed timeline and attached
media from the fresh selected-project response. It has no implicit50-row cap;
optional explicit pagination is a fork extension. count/likelyUploads describe
the returned rows; observedCount records the full snapshot before explicit pagination. Entries expose IMAGE/VIDEO/OTHER, typed likelyUpload
and valid source createTime when available. Origin project identity is preserved,
with attachment scope identified separately; no ownership is widened. Signed URLs
are excluded. Completeness remains unknown, and these counts are not account
generation-history totals. See [native media boundaries](NATIVE_MEDIA.md#read-inventory-and-metadata-boundaries).

## Fresh native image/video retrieval

GET /assets/{mediaUUID}?source=google&email={configuredEmail}&projectId={projectUUID}
returns exactly `{"url": "...", "mediaGenerationId": "..."}` after a fresh owned
project snapshot and exact GetMedia identity/type check. The email is mandatory;
projectId defaults to that configured account's project. No account scan or local
asset registration occurs. Signed URLs are confidential, transient bearer links;
responses use Cache-Control: no-store. No universal URL lifetime is assumed.

Adding raw=true or raw=1 streams validated image/png, image/jpeg or video/mp4.
An explicitly supplied raw=false, raw=0 or any other value returns400.
Image downloads have a32MiB limit and must decode with exact fresh dimensions;
video downloads have a256MiB limit and require ffprobe. Generated-video URL
metadata may have null dimensions when Google supplies no measured size; the
download result uses positive dimensions measured by ffprobe. Available fresh
metadata dimensions must still match the downloaded content. Temporary server output is
removed after response completion, Range refusal, send failure or cancellation.
The default source=local retains the managed-registry metadata/download extension
and its existing raw controls, including image bytes.

SDK/CLI/direct MCP native metadata lookup also supports active owned audio UUIDs,
with width/height null and a confidential URL. Audio bytes are not supported by
these download adapters; this HTTP asset route rejects audio with400. Saved-voice
detail remains a separate endpoint. No live audio playback acceptance is implied.

The image/video URL fields match the current frontend's source-size download
accessor, including generated and uploaded variants. Downloads retain the fresh
URL, reject redirects/untrusted hosts, verify content/dimensions and compare the
metadata byte count when available. This does not upscale or guarantee that
Google preserved uploaded bytes unchanged. Unresolved incomplete inventory,
mismatched identities or invalid worker output return a masked502; this does not
establish permanent nonexistence or exact useAPI404 equivalence.

Portable mirrors:
- SDK: get_native_asset(project_id, media_id), download_native_asset(project_id, media_id, out_dir).
- CLI: gflow project get-media --project UUID --media-id UUID --profile PROFILE --json.
- CLI: gflow project download-media --project UUID --media-id UUID --output-dir DIR --profile PROFILE --json.
- MCP: gflow_get_native_asset(project, media_id, profile), gflow_download_native_asset(project, media_id, output_dir, profile).

These are synchronous reads, matching useAPI asset GET. They do not enqueue
generation jobs or persist protected URLs in a durable queue. Existing generation
direct/queued MCP routes remain separate. CLI/MCP downloads may retrieve images
as a fork extension; existing output files are never overwritten. Video decoding
requires ffprobe; image decoding uses Pillow. Invalid output destinations return
typed errors. Audio/voice/character-reference/thumbnail detail and composite
useAPI handle translation remain separate roadmap tasks.

A zero-generation BDD passed image/video download with concurrency one in18.92s.
The live samples were uploaded variants; generated URL arms have public-source
and codec evidence, with representative live coverage still owed under R12.
See [the measured source contract](../superpowers/spikes/2026-10-03-native-asset-download-contract.md).

Native portable download byte limits are32MiB for images and256MiB for videos. These are byte limits, separate from Google account resolution entitlements.


### Fresh character image detail
SDK `get_character_detail(project_id, entity_id=...)` returns ordered native
image references with fresh preview URLs and a proven reference-image thumbnail.
CLI `gflow character show --project UUID --id UUID --include-urls --json` and
MCP `gflow_character_show(include_urls=true)` expose the same detail.
Metadata-only show/list defaults remain unchanged. These are synchronous reads;
bearer URLs must not be stored in generation queues, history or logs.

REST GET `/v1/google-flow/characters/{UUID}` returns `entityId`,
`imageReferences[{workflowId,mediaId,previewUrl}]` and `thumbnailUrl` when
the selected-project relationships are positively established, with
`Cache-Control: no-store`. Existing account/project selection applies.
Voice detail distinguishes system presets from owned saved user TTS.
Unresolved or mismatched detail returns502 instead of inferring404 from a partial
snapshot. An omitted primary-media projection can be resolved from its fresh
character-owned active workflow, only after strict GetMedia proves the exact
project/media/workflow/image identity. A separately projected, typed thumbnail
can be read through its character-owned workflow without being inserted into
ordered references. All distinct image/thumbnail reads share a sixteen-read and
sixty-second budget. Contradictory projections refuse. Composite vendor refs and
thumbnail variants with no proven workflow remain open.


### Fresh saved user voice detail
Saved-TTS detail now exposes a recognized canonical base preset from the native
audio preset/speaker fields, freshly read dialogue/performance and optional audio
playback URL. A separate description remains separate from voicePerformance.
SDK get_saved_voice, CLI voice show, direct MCP gflow_get_saved_voice and REST
GETvoices/ref source=user share the decoder. Strict GetMedia matching verifies the
selected project/media/workflow and exclusive audio arm. Playback URLs are
confidential HTTPS values from the owned native response; no media fetch or
unverified universal URL lifetime is implied. REST returns no-store.
Missing playback remains optional; missing inventory is not proof of deletion.
The original selected project had no saved-user voice fixture, so that checkpoint had
source/offline proof and no newly accepted live audio playback. Existing-voice
lookup/playback is now verified; see [current voice evidence](VOICES.md#existing-saved-voices-verified-lookup-and-creation-limitation). R12 retains the full lifecycle acceptance requirement. That original checkpoint
attempted no extra paid audio generation.

#### Native image picker captions

Captions locate an owned image; they do not establish ownership. Native UUID
references use fresh project/media/workflow proof and exact thumbnail tokens.
Long captions and captions containing at-signs, line breaks or formatting
characters use one bounded safe contiguous excerpt. Blank captions use the bare
picker. A missing or duplicate exact token stops attachment before generation.
Canonical uploaded image references share this behavior. SDK, CLI, direct/queued
MCP and REST reach this shared transport without additional request parameters.

#### Project catalog traversal

`GET /assets/projects/{email}?source=google&allPages=true&maxPages=2`
follows Google's opaque returned cursors using one browser lease. Default remains
one page. `allPages` requires literal `true` or `false`; `maxPages` accepts1–100
only with `allPages=true`, default100. Local source rejects both controls.
A supplied `cursor` starts a continuation, not a full-account census.
Responses expose `returnedCount`, `pagesRead`, `paginationExhausted`,
`cursor`, `scope` and `complete:null`. Page caps preserve the continuation.
Cycles/duplicate IDs or malformed correlated responses fail explicitly.
Traversal is bounded at180seconds inside the SDK and240seconds for the REST
worker including browser startup. No catalog writes or absence-based deletion
follow this read. SDK: `list_native_projects(all_pages=True, max_pages=2)`.

#### Account project catalogs

`GET /assets/projects/{email}?source=google&includeCatalogs=true&maxProjects=1`
adds fresh typed catalogs for bounded discovered projects. It combines with
`allPages/maxPages/cursor`. `includeCatalogs` accepts literal `true/false`;
`maxProjects` requires true and an integer1–20 (default20). Local source rejects
these controls. SDK: `list_native_projects(include_catalogs=True,max_projects=1)`.
CLI and MCP controls are documented in their [usage](../USAGE.md#observed-catalogs-across-native-account-projects)
and [MCP](../MCP.md#observed-catalogs-across-native-account-projects) guides.

Additional REST fields are `projectCatalogs` (each adds a `projectId` alias to
the native SDK `project_id`), `catalogProjectsRead`, `catalogCounts`,
`catalogsCapped` and `pendingProjectIds`. Nested native records retain documented
SDK names: media/media_id, workflows/workflow_id, characters/entity_id and
user_voices/ref, each with project_id. Per-project `counts` and `complete:null`
describe observed rows. Signed URLs and raw native payloads are excluded.
Unread listed IDs remain separate from the opaque later-page `cursor`.
Catalogs and account pages share one180-second SDK deadline, with240seconds
for REST process/browser startup. No cache writes or absence-based deletion.

### R04 native character reference video
SDK reference_character_ids, CLI video reference-native --character-ref and
registered MCP gflow_generate_native_reference_video character_ref accept owned
character UUIDs. REST POST /videos with model=omni-flash accepts character_N,
or mixed image/character UUIDs in referenceImage_N. The worker classifies those
UUIDs from the same fresh project payload, preserving original slot indices;
@referenceImage_3 can bind an entity without becoming @character_1.

Characters use Q4a field10 and structured VI entity arm3, distinct from likenesses.
Actual active entity-owned projected image links and supported linked audio
metadata determine their weights. Native character/image/audio capacities are
checked before token mint or output checkpoint. Linked character audio counts
against a positive audio pool; zero audio capacity follows the frontend visual
character policy and never permits explicit audio inputs. Missing limits or
ambiguous/archived/unrelated references refuse. No entity copying occurs during
generation preflight.

This adds R2V character transport, not rendered acceptance. The free fixture
BDD passed42.07seconds with zero generation and fixture cleanup. V2V character
transport now shares fresh classification and budgets. Available direct system
presets are also audio ingredients; rendered acceptance remains R12 work. Unprojected
reference images require further ownership proof and are not guessed.


### Native video system-preset audio references
Existing audio-reference inputs accept active owned audio UUIDs or available
system presets. CLI --audio-ref Charon, SDK audio_ids/reference_audio_ids, direct
MCP audio_ref and REST referenceAudio_N accept known names (case-insensitive)
or exact voices/charon-style lowercase resources. Canonical audio-slot indices
are preserved, including REST/SDK holes. Equivalent aliases count as the same
identity and duplicates refuse.
Both R2V and V2V verify a unique current native preset-catalog entry before mint,
encode the bare lowercase resource in audio vectors and inline audio chunks,
and charge explicit presets against the observed native model audio capacity.
Unknown names, URLs/arbitrary paths, missing/duplicate catalog entries and
zero/unknown audio capacity refuse. UUID ownership/type rules remain unchanged.
This is reference transport/preflight support; accepted rendered speech is R12.


### Native supplied CAPTCHA tokens
Native reference/edit POST /videos, POST /videos/extend and POST /voices accept
captchaToken (20–20000 characters, one use). It is mutually exclusive with
captchaOrder/captchaRetry, which are supported on dedicated native paths after validation. Raw tokens
stay outside durable job JSON and are consumed through private worker files.
Exact native project/action/host binding and no fallback/replay apply.
Generic UI video supplied/provider controls require count1; configured order and explicit1–10 WAF-only retries are supported. Generic multi-output overrides remain501. Image2K/4K supports supplied/provider tokens and explicit1–10 WAF-only retries, with current4K availability checked before paid mint and dispatch. Exports use no generation override.
See [native CAPTCHA controls](NATIVE_CAPTCHA.md).

## Explicit native video promotion
POST videos/upscale accepts operation=promotion with720p/1080p/4k, optional modelKey and native CAPTCHA controls. GET videos/upscale/models discovers target-specific account models. Omitted operation selects native promotion at1080p; explicit operation=export selects legacy export. See [promotion](NATIVE_VIDEO_PROMOTION.md).

## Fresh image reference budgets
GET images/reference/models exposes advertised, transport and effective capacities using fresh account metadata. All native reference-bearing SDK requests use that effective capacity before uploads/minting. See [budget contracts](IMAGE_REFERENCE_BUDGETS.md).

Confirmed permanent-delete retries preserve requested deleted IDs, separate newly/already deleted IDs and make zero mutation calls for receipt-backed already-gone batches. Fresh account/project and exact GetMedia NOT_FOUND proof required; arbitrary absent UUIDs refuse. See [native media](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/NATIVE_MEDIA.md#confirmed-deletion-retries-r09).

## Account-load statistics (HTTP extension)
GET /jobs?options=summary returns public configured account identifiers plus images/videos/combined summary objects. options=executing adds running jobs with elapsed time; options=history adds executing and the ten newest terminal records per generation family. GET /jobs defaults to summary; source=local selects the paginated job list. Statistics options cannot combine with listing filters; invalid options return400.

Only enabled, verified registrations contribute. Image generation/upscaling and video text/reference/edit/extension/promotion jobs are counted; queued jobs, account maintenance, uploads/deletion, export/GIF and local composition are excluded. Running jobs remain visible regardless of age; terminal outcomes use a fifteen-minute window. Completed, failed and rateLimited counters are separate; recorded429 outcomes are excluded from failed. The observational score is executing+completed+10*failed+20*rateLimited. Automatic selection now uses the combined score, then queue load; native reason/model quarantine remains unsupported.

timingPolicy=accepted-to-observation-or-terminal explicitly includes queue waiting. Elapsed timestamps start at durable acceptance; responseTime and avgResponseTime are milliseconds from acceptance to terminal update. The combined average weights actual timing samples; no samples return null. This is not proof of pure execution duration. rateLimitScope=recorded-terminal-jobs excludes queue-admission429 failures that have no job. Unknown stored failure codes project to502; interrupted jobs remain502. Metadata projection exposes no prompts, cookies, CAPTCHA tokens, result bodies, protected URLs or filesystem paths.

The account and job metadata come from one SQLite read snapshot; aggregate counts do not inherit the old100-row listing cap. Current differences from [useapi GET jobs](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs) include timing provenance, excluded job types/admission failures and scheduler/quarantine behavior.

Deprecated HTTP image model aliases are normalized before validation and queue creation: nano-banana to nano-banana-2, imagen-4 to nano-banana-2-lite. Job request records expose the canonical model; Imagen itself is not restored by this alias. Direct SDK/CLI/MCP model aliases are unchanged.

HTTP image aspect aliases landscape/portrait normalize to16:9/9:16 before validation and queueing. Explicit native video promotion accepts useapi's4K spelling and stores canonical4k. Video upscale defaults to native promotion1080p; explicit operation=export retains export behavior. Fresh tier/model/source checks still determine entitlement; case normalization does not grant Pro accounts4K access. SDK/CLI/MCP controls are unchanged.


## Explicit native image/video aliases

HTTP can register an exact opaque alias for an existing owned native image/video.
POST /assets/{email}/aliases accepts alias, mediaGenerationId (native UUID), kind
(image or video) and optional projectId (the configured project by default). It
requires an enabled verified account and a fresh owned native metadata/type/URL
check before storing the binding. Repeating the same binding rechecks ownership;
a conflicting binding returns409. Registration returns201 with alias,
mediaGenerationId (alias), nativeMediaGenerationId, projectId, kind and verified.
No signed URL is persisted with the mapping.

Supported syntax is user:OPAQUE-email:OPAQUE-image:UUID, or video:UUID. Prefixes
use only ASCII letters, digits and . _ ~ -; user is1–128 characters and email
is1–512, with a1024-character total cap. These are opaque local labels, not decoded
useapi user/account identities. The media suffix must match the explicit UUID.
Character/voice aliases use the separate explicit resource routes below; arbitrary
vendor identity decoding remains unsupported. Exact registered HTTP inputs are
resolved through the explicit bounded paths documented below.

```python
media_uuid = "11111111-1111-4111-8111-111111111111" # replace with an owned image
alias = f"user:local-email:account-one-image:{media_uuid}"
registered = client.post("/assets/account-one/aliases", json={
    "alias": alias, "mediaGenerationId": media_uuid, "kind": "image",
})
registered.raise_for_status()
read = client.get(f"/assets/{alias}", params={"source": "google"})
read.raise_for_status() # confidential transient URL; do not log it
removed = client.delete(f"/assets/account-one/aliases/{alias}")
removed.raise_for_status()
```

GET /assets/{alias}?source=google resolves only a registered exact binding and
performs a fresh native read. Optional email/projectId must match the binding.
The JSON response echoes the alias as mediaGenerationId and uses no-store.
raw=true/1 supports validated images and videos; other supplied raw values refuse. Unregistered
aliases return404 for the local mapping, not proof that Google media is absent.
Malformed read aliases return400; registration validation returns422. Ownership
or scope failures refuse, and unresolved native metadata returns502.

DELETE /assets/{email}/aliases/{alias} removes only the scoped local mapping,
returning removed:true, googleMediaDeleted:false and scope:local-alias; unknown
mappings return404 and foreign scope403. This does not delete Google media.
SDK/CLI/MCP image/video get/download reads accept these exact local mappings
when the caller explicitly selects the enabled registered profile and project.
They must use the same private GFLOW_SELFHOST_ROOT as REST; another machine does
not automatically have its mappings. SDK selects the owning profile_dir; CLI
requires --profile and MCP requires a nondefault profile argument. Fresh reads
verify native identity and registered media kind. Unknown UseAPI references have
no inferred account or decoded UUID fallback. SDK/CLI/MCP generation and mutation
inputs retain their existing raw contracts. Full vendor encoding/error equivalence
is not claimed.


## Bounded native account history

GET /assets/projects/{email}?source=google&includeHistory=true adds accountHistory
to existing project discovery. Optional historyCursor, historyMaxPages (1–50)
and historyMaxMedia (1–1000) require includeHistory=true/source=google. Defaults
are50 pages/1000 media with a45-second history deadline and fixed20-workflow
requests; the project inventory cursor and allPages controls remain independent.

```python
history = client.get("/assets/projects/account-one", params={
    "source": "google", "includeHistory": "true", "historyMaxPages": 2,
    "historyMaxMedia": 100,
}).json()["accountHistory"]
# Pass history["next_cursor"] back as historyCursor to continue.
```

The nested accountHistory DTO retains native snake_case fields: workflows with
workflow_id/project_id and optional primary_media_id; media with stable native
identities/kinds and available dimensions; next_cursor, pages_read, returned_count
(workflows), media_returned_count, capped, timed_out, pagination_exhausted and
complete:null. The scan preserves whole verified pages and continuation at a cap.
It never returns captions, prompts or protected URLs. Cursor exhaustion does not
prove snapshot consistency or complete account history. Counts are per-call
observations, not useapi generated-only project total/byType/date aggregation.
No absent row authorizes deletion or GetMedia ownership.

REST includeHistory also returns inventoryObservations with durable observed
workflows/media/project counts, complete:null and an explicit observation scope.
The private metadata cache upserts only validated identities, types, dimensions
and optional source times under the exact profile/configured-account pair. It
stores no URLs, prompts, captions or cursors. Missing rows remain observed rather
than deleted; counts accumulate observations, not complete or current inventory.
This REST-only cache never authorizes GetMedia, generation references or deletion.
SDK/CLI/MCP do not create it.


## Explicit character and saved-voice aliases

HTTP resource aliases bind existing owned native detail, never decoded vendor
identity. Prefixes follow the image/video URL-safe opaque subset above. Character
syntax: user:X-email:Y-character:ENTITY_UUID-imgs:1 (or2), optionally suffixed
with -voice:SAVED_VOICE_WORKFLOW_UUID. Saved voice syntax:
user:X-email:Y-voice:WORKFLOW_UUID-mid:AUDIO_UUID.

POST /characters/{configuredAccount}/aliases accepts alias, entityId and optional
projectId (configured default). Fresh owned character detail must match the exact
entity/project and image count; a separate thumbnail does not count as an image
reference. An optional voice suffix requires fresh active source=user saved-voice
workflow/audio proof in that project; a system preset does not satisfy it.

POST /voices/{configuredAccount}/aliases accepts alias, mediaId, workflowId and
optional projectId. Fresh saved-voice detail must prove the exact owned audio UUID,
workflow/project and protected playback URL. Unresolved/deleted playback refuses.
Registration returns201 after fresh verification; repeated identical mappings
reverify, and conflicting immutable bindings return409. No protected URL is stored.

```python
entity_uuid = "11111111-1111-4111-8111-111111111111" # replace with an owned character
alias = f"user:local-email:account-one-character:{entity_uuid}-imgs:1"
created = client.post("/characters/account-one/aliases", json={
    "alias": alias, "entityId": entity_uuid,
})
created.raise_for_status()
detail = client.get(f"/characters/{alias}")
detail.raise_for_status() # confidential detail URLs: do not log
client.delete(f"/characters/account-one/aliases/{alias}").raise_for_status()
```

GET /characters/{alias} and /voices/{alias} derive account/project from the exact
registered mapping and revalidate fresh detail. Voice alias reads default to user
detail; explicit foreign email/projectId returns403. Responses expose ref as the
alias, nativeRef as the raw entity/audio UUID and confidential transient detail
URLs under Cache-Control:no-store. Missing local mapping404 is not proof that
the Google resource is missing; unresolved native ownership/detail returns502.

DELETE /characters/{account}/aliases/{alias} or /voices/{account}/aliases/{alias}
removes the scoped local mapping only, returning googleResourceDeleted:false.
It performs no Google resource mutation. The generic HTTP asset endpoint rejects
character/voice aliases with400. Supported generation/operation fields now resolve
registered aliases explicitly; Google resource deletion and character CRUD
mutation inputs are not widened. SDK get_character/get_character_detail and
get_saved_voice, CLI character show/voice show and direct MCP detail twins accept
exact locally registered aliases with explicit owning profile/project and the
same GFLOW_SELFHOST_ROOT. Fresh detail must match registered image-count and
optional saved-voice workflow declarations; saved-voice aliases require the exact
fresh audio workflow. Unknown vendor prefixes are never decoded. At the 4 October checkpoint, saved-user audio and voice-alias fixture proof
remained pending. Actual character-alias REST lifecycle passed without generation
or Google mutation. The 5 October closure below supersedes the voice fixture
limitation; exact vendor contract equivalence remains R11.


## Explicit native catalog resume

GET /assets/projects/{email}?source=google&includeCatalogs=true&catalogProjectIds=UUID1,UUID2
resumes catalog enrichment for1–20unique explicit project UUIDs in caller order.
maxProjects caps the reads; pendingProjectIds retains ordered remaining IDs.
Account cursor/allPages/maxPages are incompatible. Each selected project uses
the same fresh owned payload; no account project discovery is performed.

```python
resumed = client.get("/assets/projects/account-one", params={
    "source": "google", "includeCatalogs": "true",
    "catalogProjectIds": ",".join(pending_project_ids), "maxProjects": 1,
})
resumed.raise_for_status()
```

Response projects:[], pagesRead:0, paginationExhausted:null and catalogResume:true
express that no account pages were scanned. projectCatalogs, catalogCounts,
catalogProjectsRead, pendingProjectIds and catalogsCapped retain existing meanings
and caller order. No project names or complete account inventory are fabricated.

REST inventoryObservations now also counts metadata-only observed projects
(including empty projects), characters and user_voices accumulated across scans.
Only source:user saved-voice/audio/workflow identities are recorded; system presets
are excluded. Exact profile/configured-account scope and transactional conflict
rollback apply. URLs/prompts/captions/cursors are never persisted; missing rows
are retained and complete remains null. Attached origins do not become selected
project ownership; cache contents never authorize GetMedia, generation or deletion.
SDK/CLI/direct MCP retain read-only native DTOs and do not persist this REST cache.


## Registered aliases as HTTP inputs

Supported HTTP generation/operation fields accept exact registered image/video/
character/saved-voice aliases. A shared resolver runs before account selection,
reference planning and queueing. All bindings must share the exact configured
account/profile/project; omitted email/projectId derive from that scope. Matching
explicit scope is accepted, foreign scope403, mixed bindings409, unknown mapping404
and wrong kind400. Fresh account verification, native media type/URL or character
count/saved-voice declarations are rechecked before admission. Prefixes are not
decoded or trusted as ownership.

| Operation | Alias fields and kinds |
| --- | --- |
| POST images | reference_1..10:image; character_1..7:character |
| Image upscale | mediaGenerationId:image |
| Native R2V | referenceImage_1..7:image or character; referenceAudio_1..5:saved voice; character_1..7:character |
| Native video editing | referenceVideo_1:video; referenceImage_1..5:image or character; referenceAudio_1..3:saved voice; character_1..7:character |
| Video extend/upscale/GIF | mediaGenerationId:video |
| General video | startImage/endImage/referenceImage_1..7:image |

Native video mixed image/character slots retain existing fresh SDK classification
and positional markers. Ordinary image reference_N accepts images only. Preset
strings remain unchanged; saved-voice aliases become owned audio UUIDs. General
POST /videos image aliases now populate the required private managed cache from
a fresh verified native image before admission. The private worker validates
PNG/JPEG content with a20MiB cap into a profile/project-scoped UUID directory;
atomic store insertion preserves that scope. Cache failures return502 without
queueing generation; an existing foreign cache refuses422. Unregistered raw UUID
behavior and public native image GET remain unchanged. Local export/GIF controls
and model entitlements retain their existing prerequisites. Alias resolution does not make unsupported transport
inputs work.

Queued requests contain canonical UUIDs in the original numbered positions;
protected URLs, signatures and tokens are not persisted. An image alias and raw
UUID naming the same image retain intentional deduplication with slot order;
existing video duplicate validation still refuses duplicate logical references.
Existing workers repeat fresh scope/ownership checks. SDK/CLI/MCP generation
UUID inputs and preset names are unchanged; Google media DELETE and character CRUD mutation
alias inputs remain outside this batch.

```python
queued = client.post("/images", json={
    "prompt": "A ceramic mascot on a blue background",
    "reference_1": registered_image_alias, "count": 1, "async": True,
})
queued.raise_for_status()
#201 means accepted into the queue. Poll the job to establish generated output.
```

Actual workers-disabled forwarding/cache/queue BDD passed64.71seconds with zero
generation. Final gates passed6746tests. Paid accepted output remains unproved.
Sourceea9cc2c5 is published/deployed with all3 production default-history
HTTP200 reads and zero generation. Queue acceptance does not establish rendered acceptance; an
explicit Google WAF refusal or unknown outcome is recorded separately.


### Generated-history summaries and HTTP defaults

The R03 batch implements useapi generated-history project counts, distinct from
project inventory counts. Actual default-summary/media BDD passed65.84seconds with zero generation;
final frozen-source gates passed6746tests,5skips,89%coverage; sourceea9cc2c5 is published/deployed with all3 production default-history
HTTP200 reads and zero generation. Positive generated
image/video arms alone supply per-call projectId/isCurrent/total/byType and
optional oldest/newest source dates; uploads/audio/unknown are excluded. scanned
includes all observed media. Up to50pages/20-workflow requests/45seconds with
truncated/cursor and stoppedOn:timeBudget preserve continuation, without global
completeness claims. SDK history and existing CLI/MCP include_history gain additive
summary fields, without new public flags/tools.

HTTP default change: assets/projects source=history; explicit source=google
keeps project inventory/catalogs and source=local keeps cached listing. assets/media
default source=google keeps whole observed native project; source=local selects
the managed cache. This changes the prior implicit local-list defaults. Existing clients requiring
managed caches should now explicitly supply source=local.

Default GET /assets/projects/{email} (or source=history) accepts only optional
cursor, not native catalog/traversal controls. Projects are sorted by generated
total descending and include projectId, isCurrent, total, byType with IMAGE/VIDEO
counts and optional oldest/newest valid UTC dates. isCurrent compares the actual
configured project. Each continuation response contains its own scanned counts;
merge totals/byType and outer date bounds yourself for a multi-call view. Empty
generated cohorts return empty projects even when excluded media were scanned.
scanned includes verified observed media of all types, including excluded uploads/
audio/unknown. It is not a global count. truncated/cursor indicate unread bounded
history; stoppedOn:timeBudget indicates the45-second deadline. complete:null
retains the consistency limitation even after cursor exhaustion.

SDK list_native_history and CLI/MCP include_history keep their existing options
and add media generation_source/likely_upload, scanned, project_summaries and
continuation flags. Native summary names remain snake_case (project_id, by_type
with image/video counts, stopped_on); HTTP default summary projects use camelCase
and uppercase media type names. No new public MCP tool/CLI flag is added.


## 4 October delivery additions
- GET /jobs defaults to summary; source=local selects the durable list. Conflicting
  modes refuse. Automatic selection ranks eligible accounts by the existing
  last15minute combined score, queue load, then stable profile order. Explicit
  accounts and owned references remain pinned. Quarantine is not inferred.
- GET /voices with email defaults to fresh combined system and selected-project
  user catalogs. Explicit source modes remain. Both reads revalidate one scope;
  saved-user list entries omit protected playback URLs.
- Raw image/webp uploads validate and convert to PNG for the native transport.
  Response contentType, sourceContentType, converted report actual conversion.
  Animated, malformed, mismatched or oversized WebP refuse before queueing;
  PNG/JPEG bytes retain existing handling.
- POST /assets/sync/{email} adds resumable read-only synchronization; see
  [inventory sync](NATIVE_INVENTORY_SYNC.md).
- Exact registered aliases are accepted for character creation, character/voice
  deletion and media deletion. Fresh account/project/type proof remains required.
  Confirmed deletion receipts match exact profile, identity, project and media.
- Accepted verified same-account cookie refresh activates durable profile lineage:
  aliases, recent statistics and same-payload idempotency survive that proven
  transition. Original audit records remain immutable. Account removal closes
  lineage; unrelated registration cannot adopt old jobs/references. Private deletion
  receipts transfer only after exact identity/scope verification.
- Dedicated native generation supports explicit configured provider order and
  bounded confirmed-refusal retries; see [CAPTCHA](CAPTCHA.md). Image UI solving,
  generic video overrides and upscale controls retain their separate boundaries.

Successful live cookie import, accepted video/TTS rendering, Ultra-only4K, arbitrary
vendor IDs and complete global inventory remain independently recorded gaps.

### Native concatenate and updated defaults
POST /videos/concatenate accepts2–10 managed video references, exact registered
native aliases, or raw owned native UUIDs pinned by explicit email/projectId.
Every native input is freshly owned/type-validated before download, then decoded
and dimension-checked in a private bounded cache (256MiB per input,180seconds
overall). Same account/project/dimensions and valid duration/trims are required.
Repeated input positions are preserved; downloads may deduplicate. The result
includes integer inputsCount and a managed local ffmpeg output, not Google editing.

POST /videos/upscale defaults to operation=promotion,resolution=1080p.
Explicit operation=export retains legacy exports. Fresh entitlement and model
checks remain mandatory. Image callbacks allow5seconds; other callbacks10seconds,
with the existing public-HTTPS/DNS/streaming limits.

Current CAPTCHA coverage: images and dedicated native reference/edit/extension/
promotion/TTS accept provider selection and explicit WAF-only retry1–10.
Generic UI videos accept supplied/provider controls at count1 with explicit1–10 WAF-only retry. Native image2K/4K supports supplied/provider controls and explicit1–10 WAF-only retry;4K requires current enabled availability before mint and dispatch.
See [CAPTCHA](CAPTCHA.md) for one-use, acknowledgement and unknown-outcome rules.


## Account resource continuation and generic video providers
See [observed account resources](ACCOUNT_RESOURCES.md) for SDK/CLI/direct MCP/HTTP query bounds, epoch-scoped opaque cursors, URL-free results and completeness limits. Existing /characters and /voices defaults remain project-scoped; this extension does not silently redefine them. See [generic video CAPTCHA](GENERIC_VIDEO_CAPTCHA.md) for count1 SDK/CLI/queued MCP/REST provider controls. Queued confidential tokens refuse before enqueue; ordinary configured providers do not activate merely by saving a key.


Text-only multipart requests now share the JSON mutation handlers. See [form requests](FORM_REQUESTS.md) for exact field conversion, duplicate/file refusal and private token lifecycle. Native binary asset uploads retain their separate contract.

Generic count2–4 videos use one native request and retain every actual output; provider controls support the same range. See [batch results](VIDEO_BATCH.md), [text forms](FORM_REQUESTS.md) and [local quota routing](ACCOUNT_SCHEDULER.md).


## Fresh per-image upscale capabilities

GET /v1/google-flow/images/upscale/capabilities reads exact owned-image2K/4K detail-menu availability synchronously. Use email/projectId/mediaGenerationId; states are available/disabled/unknown with nullable availability and no inferred subscription entitlement. No generation job is created. See [capability reads](IMAGE_UPSCALE_CAPABILITIES.md).

Generic image CLI and durable MCP provider controls are documented in
[GENERIC_IMAGE_CAPTCHA.md](GENERIC_IMAGE_CAPTCHA.md). REST retains its existing
image policy and private supplied-token path; queued MCP serializes no tokens.


### R02 saved-voice lookup closure — 5 October 2026

The earlier missing saved-user fixture limitation is superseded: SDK, CLI, REST
and registered HTTP MCP passed existing saved-voice detail/playback and exact
registered voice-alias reads. REST returns no-store and the fresh Google audio URL
returned 200 with a valid 7.8-second mono 24 kHz WAV. Alias registration accepts the
actual typed decoder contract without a catalogue-only source discriminator;
exact account/project/media/workflow, playback URL and explicit deleted/non-user
checks remain. Unknown vendor references are not inferred. Backend voice creation
remains Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY; its cause is unknown.
R02 lookup is complete; full voice CRUD/binding acceptance remains R12. See
[voice usage and limitations](VOICES.md#existing-saved-voices-verified-lookup-and-creation-limitation).

### R03 synchronization progress and account binding

`POST /v1/google-flow/assets/sync/{email}` retains its existing bounded body
(`maxSteps`, `maxSeconds`, `restart`) and now shares the scoped SDK sync method
with CLI and MCP. The registered account's private recorded principal is captured
before dispatch and checked before worker commits and REST publication. Missing or
changed principal returns409; no profile is substituted.

Responses add `checkpoint_version`, `scan_id`, current traversal page counters,
`retained_unique_counts` and `deletion_authority=false`. Existing per-scope
`observations` remains compatible. Retained counts include prior scans and are not
fresh visibility claims. Repeat until `traversal_finished`, or explicitly restart
without deleting observations. Unsupported catalog/cursor reads return an error
with earlier committed progress retained. See
[full progress semantics](NATIVE_INVENTORY_SYNC.md#r03-supported-traversal-and-progress).


### R04 reference closure

Native video model endpoints return max_images, max_audio and max_characters from
fresh account data. R2V/V2V share active exclusive native-audio/workflow proof;
UUID audio need not be saved-TTS visible. Exact registered saved-voice aliases
continue to require actual saved-user resources. Existing referenceImage_N,
referenceAudio_N and character_N fields retain original positions into the workers.
CLI --reference-slot and direct MCP reference_slot_ids now expose the same mapping.
Live existing-audio final request construction passed before token mint/submission;
current fixtures lack unsaved uploaded-audio coverage. Rendered acceptance is R12.
See [supported inputs](NATIVE_REFERENCE_VIDEO.md#r04-supported-reference-inputs-and-implementation-closure).


## R07 native resolution usage and limits

Image `upscale` selects2k(default) or4k; video `upscale-native` selects720p,
1080p(default) or4k. Read `image upscale-capabilities` and `video upscale-models`
first using the exact original profile/project/source. Direct MCP mirrors these
reads and operations; REST provides `images/upscale/capabilities` and
`videos/upscale/models`, plus existing private operation workers. Supplied tokens
remain confidential, exclusive and one use; provider retries are explicit and
only positively confirmed WAF refusal can permit another attempt. Fresh ownership,
model/target/aspect limits precede minting. Accepted/unknown work never replays.

Read-only CLI example (no upscale):
```sh
gflow video upscale-models --profile pro2 --project PROJECT_UUID --resolution 720p --json
```
Read-only REST example through the workstation's existing SSH forward:
```sh
curl -H "Authorization: Bearer $GFLOW_DAEMON_TOKEN" \
  'http://127.0.0.1:8844/v1/google-flow/videos/upscale/models?email=ACCOUNT_HANDLE&projectId=PROJECT_UUID&resolution=720p'
```
Authenticated bearer values stay private. MCP reads use
`gflow_list_video_upscale_models(project=PROJECT_UUID,resolution="720p",profile="pro2")`
and `gflow_get_image_upscale_capabilities(project=PROJECT_UUID,media_id=IMAGE_UUID,profile="pro2")`.
Enabled/disabled/unknown image menu observations and available/empty/error video
catalogs describe current scoped observations, not subscription or generation proof.
Native promotion is distinct from export, download, GIF and local resizing.

Implementation complete, paid acceptance pending. Both active video allowances
remain exhausted. Existing accepted browser2K output is valid; new solver-backed
upscale, accepted promotion and entitled4K outputs need separately authorized R12
operations and solver/credit allowances. See
[native promotion](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/NATIVE_VIDEO_PROMOTION.md)
and [image capabilities](https://github.com/Fograd/gflow-cli/blob/develop/docs/self-hosted/IMAGE_UPSCALE_CAPABILITIES.md).


### R08 supported image reference closure

See [reference budgets](IMAGE_REFERENCE_BUDGETS.md) for forms, fresh independent
image/character limits, actual character weights, ordering, Auto and exact accepted
ten-reference evidence. Existing controls only: model aliases, integer count1–4,
32-bit seed+count range and five explicit ratios. Invalid controls refuse; no
new controls were added. Controlled queued MCP tests use a temporary queue and
stop before mint/submission. Per-reference rendered influence remains R12.
