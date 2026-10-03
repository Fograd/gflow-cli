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
| `GFLOW_SELFHOST_SYNC_WAIT_SECONDS` | Default 600; range 0–900; per-route ceiling 600 seconds (concatenation 180); zero returns HTTP 408 immediately while processing continues |
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
| `GET /accounts`, `/accounts/{handle}` | Read registered profiles and operator-attested or native-cookie-verified health |
| `POST /accounts`, `DELETE /accounts/{handle}` | Register an existing operator-attested profile or import a bounded private cookie table into a staged new/refresh profile after actual identity and project-access checks; deletion removes registration only |
| `POST /accounts/{handle}/health` | On-demand native project-access check through the serial queue; supports async and callbacks; preserves the saved profile and does not refresh login. See [session health](SESSION_HEALTH.md). |
| `POST /images` | Text or registered image references; three Nano Banana model aliases, five image aspects, count 1–4 |
| `POST /images/upscale` | Native Google upscale via the fork's CLI, `resolution: "2k"` or `"4k"`; Google enforces plan entitlement |
| `POST /assets`, `/assets/{handle}` | Raw PNG/JPEG/MP4 upload, maximum 20 MiB; synchronous tee-compatible response |
| `GET /assets/{id}`, `/assets/{id}/download` | Managed metadata/bytes by default; source=google fresh owned image/video URLs and video-only raw |
| `GET /assets/projects/{handle}` | Local catalog by default; source=google reads paginated native account projects |
| `GET /assets/media/{handle}` | Managed catalog by default; source=google reads selected-project native timeline |
| `GET /jobs`, `/jobs/{id}` | Durable jobs; list filters email/status/kind plus limit/cursor |
| `DELETE /assets/{handle}` | Native reversible whole-batch archive by default; operation=delete permanently removes only selected owned media IDs; explicit localOnly cache deletion is separate |
| `POST/GET /accounts/captcha-providers`, `GET /accounts/captcha-stats` | Private solver configuration/statistics; provider generation guarded with HTTP 501; see CAPTCHA.md |
| `GET /voices`, `/voices/{ref}` | Bundled presets by default; catalog=google reads native presets; source=user reads owned saved TTS voices and fresh detail playback URLs |
| `POST /voices`, `DELETE /voices/{ref}` | One TTS preview plus two metadata saves; permanent saved voice deletion; durable jobs; see [saved voices](VOICES.md) |
| `GET /characters`, `/characters/{ref}` | Native project summaries/detail |
| `PATCH/DELETE /characters/{ref}` | Native metadata changes/removal; inspect unconfirmed outcomes before retry |
| `POST /characters` | Native one/two-image creation with initial notes and system preset or owned saved TTS voice assignment |
| `POST /videos` | Text, start/end image or image-ingredient video; referenceVideo_1 selects native Omni editing with frame trims, up to5 image/3 saved-audio references; ordinary Omni image/audio ingredients use the dedicated native adapter; explicitly enabled |
| `POST /videos/extend` | Native standalone continuation outputs, count1–4; optional modelKey discovered by account tier/source aspect; see [extension](NATIVE_VIDEO_EXTENSION.md) |
| `GET /videos/extend/models`, `/videos/edit/models`, `/videos/reference/models` | Fresh native model keys and credit costs for the selected account/project |
| `POST /videos/upscale`, `/videos/gif` | Native export adapter: 1080p or original 720p, 270p GIF; no new generation |
| `POST /videos/concatenate` | Local ffmpeg equivalent on 2–10 managed MP4 clips; same account, same dimensions and valid trims |

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

System voices use `source=system`; the default is the bundled catalog and
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

Image requests accept a native integer `seed` with room for `count` consecutive
seeds (`0..2147483647-count+1`); see [seed evidence](SEEDS.md). Image-only supplied-token rewriting and provider configuration are described in [CAPTCHA.md](CAPTCHA.md). `captchaToken` has a one-shot transport override; live replacement acceptance is
unverified. `captchaOrder` and `captchaRetry` return501 before queueing because replacement-token acceptance remains unverified despite measured native action metadata. Provider keys alone do not enable generation.

Image Auto aspect uses a labelled first-reference approximation across REST, CLI,
MCP and reference batch manifests. Saved TTS lifecycle, saved-voice character binding,
individual permanent media deletion, native standalone extension and Omni editing
are implemented from the deployed frontend codecs. A later native metadata read
confirmed removal of one owned synthetic clip after delayed visibility; the final owned synthetic lifecycle subsequently passed in 28.91 seconds, with all originally active media preserved. The first saved TTS attempt was ambiguous with no acknowledged handles. After correcting its proven preset-case divergence, one captured no0P6 request was explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7). No audio or saved-voice binding lifecycle was accepted. One native R2V browser-token
attempt was explicitly rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY. Extension,
editing and saved-voice binding acceptance remain pending. Still unsupported: canonical video positional grounding,
full native library synchronization, numerical video seeds and video CAPTCHA
overrides. Unknown controls return501.

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
accepts active owned native audio media UUIDs, including uploaded audio without saved-TTS visibility. System preset names and character IDs remain separate R04 work. Count
is1 and aspect follows the source. The SDK performs fresh native ownership checks.
Results retain resolved `startFrameIndex` and `endFrameIndex`;
`sourceDurationSeconds` is present when measured for an omitted end. These fields
survive synchronous response, job polling and callbacks. Read [video editing](../VIDEO_EDIT.md)
for CLI/MCP and SDK equivalents.

Lists accept `limit` 1–100 and opaque `cursor`; jobs also accept `email`, `status`
and `kind`, managed media accepts `projectId`, and `source=google` for a native selected-project timeline; asset lookup accepts `raw=true`; source=google native lookup also accepts email/projectId and requires explicit account selection
for protected bytes. Unknown or repeated query keys are rejected. Default catalogs are local. Native timeline rows carry media_id/workflow_id, caption, archived and batch_media_ids plus mediaGenerationId/projectId aliases; they do not claim merged attached-media history or inferred media types.

Account registration accepts `profile`, `email`, `projectId`, `enabled` and
`verified`. Defaults are disabled/LOGIN_REQUIRED. Enabling requires `verified:true`
and an existing local profile; this is operator attestation, not a Google probe.
Removing registration refuses active jobs and keeps the browser profile. Local
asset deletion with `localOnly:true` requires `mediaGenerationIds` (up to 100) or
`projectId`, refuses active references and never changes the Google library. Without localOnly, DELETE requires projectId and 1–100 distinct media UUIDs, queues reversible native archive, and validates the entire selected-project batch before mutation. All siblings in a generation batch must be selected. After successful upload/archive acknowledgement, poll the timeline for visibility; do not retry the mutation merely because a listing is stale. Explicit `operation:"delete"` selects permanent individual deletion after fresh
ownership checks and preserves unselected siblings. Already-gone idempotence is
not implemented. The new permanent-delete path awaits final E2E verification.

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

Native character and voice reads accept optional `projectId`, defaulting to the configured project. Character summaries expose `ref`, `projectId`, `displayName`, `workflowIds` and optional `thumbnailMediaId`; they are project-scoped, not account-wide useapi character CRUD. Native detail/metadata patch/delete adapters are implemented below. One/two-image POST creation has native adapter and deployed HTTP lifecycle proof; Canonical SDK image grounding has one accepted native proof. CLI/MCP/HTTP image acceptance remains pending after safe picker refusals; video grounding remains a gap. Native system voices are fetched dynamically (30 presets observed); default bundled voices remain available. `GET /voices/{ref}` uses the selected catalog. Saved preset-based TTS creation, project-scoped user listing/detail/deletion and
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
canonical grounding and accepted image output are separate proofs. Unregistered
native REST references remain part of the native lookup backlog.

### Automatic image aspect

REST managed local-image references support `aspectRatio:auto` through a labeled local policy: derive the nearest supported ratio from the first ordered decoded reference. Nano2/Pro image-to-image defaults use this policy; Lite retains its explicit default. Results preserve requested/resolved aspect and policy metadata. This is an approximation, not an observed native Google Auto sentinel. CLI/MCP and manifest rows now support first-local-reference Auto through the same
policy. CLI/MCP also resolve a first native image UUID from fresh owned selected-project
dimensions; text-only/character-only Auto refuse. REST still requires registered
managed image assets, so unregistered native UUID lookup remains a separate gap.
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

The registered MCP surface contains 37 tools: the prior 24 plus 13 feature adapters. Native credit inspection and model/catalog reads passed live. This does not prove paid rendering or full vendor parity. A controlled CapSolver Enterprise v3 proxyless VIDEO_GENERATION trial solved one token, submitted once and was rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7); accepted outputs were zero and no retry occurred. Current implementation and these scoped proofs do not establish successful import or generation across all three Google accounts.

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

## Fresh native image/video retrieval

GET /assets/{mediaUUID}?source=google&email={configuredEmail}&projectId={projectUUID}
returns exactly `{"url": "...", "mediaGenerationId": "..."}` after a fresh owned
project snapshot and exact GetMedia identity/type check. The email is mandatory;
projectId defaults to that configured account's project. No account scan or local
asset registration occurs. Signed URLs are confidential, transient bearer links;
responses use Cache-Control: no-store. No universal URL lifetime is assumed.

Adding raw=true or raw=1 streams verified video/mp4. An explicitly supplied
raw=false, raw=0 or any other value returns400; images with raw return400.
Raw downloads have a256MiB limit and require ffprobe. Temporary server output is
removed after response completion, Range refusal, send failure or cancellation.
The default source=local retains the managed-registry metadata/download extension
and its existing raw controls, including image bytes.

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
The selected project has no saved user voice fixture, so this enhancement has
source/offline proof and no newly accepted live audio playback. R12 retains that
acceptance requirement; no extra paid audio generation was attempted.

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
inputs and direct system-preset audio remain subsequent R04 work. Unprojected
reference images require further ownership proof and are not guessed.
