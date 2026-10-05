# Portable native MP4 upload and reversible archive

The SDK, CLI, MCP and self-hosted worker share native MP4 ingestion and whole-batch move to trash. They perform no video generation. MP4 identification checks a leading bounded ftyp box; it does not decode every frame or establish a Google file-size guarantee. The local snapshot budget is 250 MiB; the REST upload body cap remains 20 MiB.

Every upload now requires an explicit per-request rights assertion. CLI uses --rights-confirmed, MCP/SDK require rights_confirmed=True, and HTTP requires the exact header X-Flow-Rights-Confirmed: true. Missing or false HTTP consent fails 422 before enqueue. This is a deliberate strengthening of the fork contract. No account-wide consent preference is stored.

~~~bash
gflow project upload-video clip.mp4 --project PROJECT_UUID --rights-confirmed --profile PROFILE --json
gflow project archive --project PROJECT_UUID --media-id MEDIA_UUID --confirm-archive --profile PROFILE --json
~~~

~~~python
from pathlib import Path

uploaded = await client.upload_native_video(
    project_id=project, path=Path("clip.mp4"), rights_confirmed=True
)
archived = await client.archive_native_media(
    project_id=project, media_ids=[uploaded["media_id"]], confirm_archive=True
)
~~~

MCP mirrors are gflow_upload_video(path, project, rights_confirmed=True, profile) and gflow_archive_media(media_ids, project, confirm_archive=True, profile). These are direct bounded operations, without queued replay. Public adapters create the private immutable snapshot before creating a browser client; SDK methods validate consent and identifiers before checking out a page from an already-open client.

Archive is reversible whole-batch move to trash. Include every measured active owned sibling in each batch. Fresh native preflight refuses missing, ambiguous, archived or foreign membership before the first write. A 100-item request bound is not evidence that the native timeline always exposes every sibling or that all possible batches are supported. Neither operation deletes local source files.

A possible write with lost acknowledgement raises NativeMediaMutationUnknownError (exit 40). Safe fields include operation, phase, selected project and bounded known/pending media UUIDs. No automatic retry occurs. Known upload IDs are inspection handles, not a completed local asset registration. Partial archive acknowledgements survive the failure; inspect these and pending handles before another request. Cancellation stays cancellation with typed private recovery metadata. Snapshot cleanup and browser teardown failures after an acknowledged operation retain known handles.

Offline source/adapter tests cover consent, duplicate aliases, unsafe files, mutation uncertainty, cleanup/teardown, public projections and CLI/MCP parity. Credit-free synthetic SDK and public CLI ingestion/archive lifecycle proofs passed in 54.80 and 57.56 seconds respectively. Each made one upload and one archive attempt, preserved all originally active media, and used no generation or automatic mutation retry. Registered MCP protocol lifecycle also passed in 67.96 seconds through an isolated authenticated server, with original media preserved. HTTP lifecycle passed in 51.86 seconds through an isolated fresh-state API, with exactly one completed upload job and one completed native archive job and original media preserved. An earlier test URL mistake returned 404 before enqueue (zero durable jobs); its allowance was preserved and a separately authorized fresh proof used the corrected API prefix. Earlier native-worker ingestion/list/archive proof remains in the verification ledger. No paid video or speech proof is claimed.

## Permanent individual deletion

SDK delete_native_media and CLI project delete-media permanently target only requested owned identities. Every present ID passes a fresh GetMedia ownership/type check before at most one BatchDeleteAssets request. A missing ID requires the confirmed deletion receipt described below. The payload contains media IDs and no workflow IDs; unrequested siblings are not included. Explicit true confirmation and 1–100 distinct UUIDs are required. UUID spellings are canonicalised and duplicates collapse in first-occurrence order before the distinct-ID limit is checked. Every supplied value must still be a valid UUID; 101 distinct IDs refuse before browser access. SDK, CLI, direct MCP and the REST worker use this same validator. HTTP first resolves exact registered image/video mappings, then applies the same ordered normalization, including alias/UUID duplicates. Archive retains its separate whole-batch and distinct-input contract.

~~~bash
gflow project delete-media --project PROJECT_UUID --media-id MEDIA_UUID --confirm-delete --profile PROFILE --json
~~~

NativeMediaMutationUnknownError operation delete preserves pending IDs after an unconfirmed response. Never replay automatically. Reversible whole-batch archive remains separate. The media-only wire is derived from the deployed frontend source. One final owned synthetic clip received an empty acknowledgement, remained in an immediate project read, then disappeared from a fresh project timeline; exact GetMedia subsequently returned native not-found (gRPC 5) with no owned media reply. This proves deletion of that acknowledged fixture, with delayed read visibility. It does not establish a guaranteed visibility interval, all media types or preservation of every possible sibling structure. The final separately authorized synthetic upload/delete lifecycle with bounded read-only polling passed: one test passed and four skipped in 28.91 seconds, with every originally active media identity preserved.

Upload readiness is established by the native add-menu becoming visible; a hidden classic settings button alone does not show that native upload is unavailable. The corrected readiness check reached the upload menu in the final synthetic fixture run.

## Confirmed deletion retries (R09)

The fork records each strictly acknowledged permanent deletion in private profile metadata, scoped to the freshly verified Google account, project, canonical media UUID and exclusive media type. A repeat request is accepted only when exact fresh GetMedia reports native NOT_FOUND (gRPC5) and a matching receipt exists. Unknown missing UUIDs, authorization errors, malformed responses and inventory absence refuse the whole batch before any write.

Fresh same-session identity must resolve uniquely on Google's account-index-zero page. The selected project must be positively found within two current account project-list pages; a truncated listing never proves deletion. Ambiguous identity, another account/project/profile or malformed/public/symlink receipt files refuse. Request preflight is bounded120seconds.

For mixed batches, only freshly present IDs enter one permanent deletion RPC. An all-confirmed-gone batch makes zero mutation calls. SDK/CLI/direct MCP preserve the canonical distinct requested `deleted` list and add `newly_deleted`, `already_deleted` and `receipt_persisted`. Self-hosted native-delete job responses preserve `deleted` and add `deletedCount`, `newlyDeleted`, `alreadyDeleted` and `receiptPersisted`. Counts include all validated requested IDs. Failed receipt persistence after Google's acknowledgment remains a known successful deletion with the persistence flag false; it does not authorize mutation replay. Cancellation during receipt persistence and SDK/service/MCP/worker teardown retain all acknowledged IDs. An uncertain mixed write retains receipt-confirmed gone IDs as known and only the still-present write targets as pending. REST job polling preserves these safe handles, operation and phase; a client disconnect does not cancel or replay the durable job.

This is narrower than [useAPI's already-gone contract](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email): its identifiers encode ownership, whereas this fork's raw UUIDs do not. Media removed outside this fork or before receipt support cannot be accepted merely because it is absent. Native audio deletion is a fork extension; useAPI's media endpoint documents image/video only.

Free owned-synthetic batch/retry BDD passed1test,2warnings in43.96seconds: three uploads, two deletion writes, zero writes for the all-gone repeat, only the third UUID in the mixed-batch write, originals preserved. No generation or CAPTCHA task occurred. Final exact-envelope/account-index/page-readiness guard regressions are verified offline separately.


### Batch and exact HTTP alias examples

```python
# SDK: repeats are normalized, then every distinct ID is freshly verified.
result = await client.delete_native_media(
    project_id=project, media_ids=[image_id, video_id, image_id], confirm_delete=True
)
# Later repeat, after exact NOT_FOUND: newly_deleted=[]; no deletion write.
repeated = await client.delete_native_media(
    project_id=project, media_ids=[image_id, video_id], confirm_delete=True
)
```

CLI repeats `--media-id`; registered MCP uses
`gflow_delete_native_media(project, media_ids, confirm_delete=True, profile=profile)`.
Both require an explicit project and keep their existing confirmation defaults.

```python
# These aliases must already be registered to this exact account/project.
response = http.request("DELETE", "/assets/account-one", json={
    "operation": "delete", "mediaGenerationIds": [registered_image_alias, video_id],
    "projectId": project, "async": True,
}, headers={"Idempotency-Key": "r09-intended-delete-one"})
job_id = response.json()["jobId"]
# Poll that same job ID after a disconnect or an uncertain result.
```

An alias is an exact local mapping, not encoded ownership. It remains registered
following Google deletion so a scoped receipt-backed repeat can resolve it.
`DELETE /assets/account-one/aliases/{alias}` removes only that mapping. Removing
the mapping prevents later alias resolution; the canonical UUID can still use
its receipt. `localOnly:true` removes managed local bytes only. The default
remote operation remains reversible `archive`; `operation:"delete"` is the
explicit permanent choice. Audio deletion retains its existing SDK extension;
this R09 live acceptance is image/video only.

HTTP DELETE /assets/{handle} accepts an omitted projectId and uses that selected account's registered project. Explicit null, malformed or non-string projectId refuses. This default applies to the self-hosted HTTP adapter; SDK/CLI/direct MCP still require their explicit project argument. Ownership checks and archive/delete selection still apply.


## Read inventory and metadata boundaries

Native read inventories merge timeline media with attached media from the fresh
GetProjectContents response. Rows preserve their origin project and identify the
selected attachment project separately; listing an attachment does not establish
ownership for deletion, archive, references or download. Recognized exclusive
uploaded image/video arms supply likelyUpload; generated arms supply the opposite
classification. Unknown/audio rows are OTHER for the HTTP mediaType projection.
Creation times come from native metadata when valid, never from the time of the
read. Counts describe returned inventory, and completeness remains unknown; this
is not account generation-history aggregation.

HTTP source=google media inventory returns all observed rows by default, without
an implicit50-row cap. Explicit pagination is a fork extension; it does not turn
the snapshot into complete generation history. count and likelyUploads describe
the returned rows; observedCount records the full snapshot before explicit pagination. Protected download URLs are excluded from list results.

SDK get_native_asset, CLI project get-media and direct MCP gflow_get_native_asset
can read exact active owned audio metadata and a confidential transient URL;
width/height are null. An exact fresh media/project/workflow join is required.
Download adapters remain image/video only, and HTTP source=google asset lookup
rejects audio with400. Audio playback and accepted video output are separate live
proof obligations.

Character thumbnails missing from the media projection can resolve through
bounded exact character detail with a positively owned parent relationship.
Unknown or ambiguous relationships refuse; missing projection is not404 proof.
The source-backed merge and typed classification do not complete R02/R03 or
establish compatibility with useapi composite references.


## Fresh URLs and raw image/video reads (R02)

Use an explicit profile and selected project for SDK/CLI/MCP lookup. The HTTP
UUID route requires a configured account; its project defaults only to that
account's registered project. Registered aliases use their exact verified scope.
No signed URL is persisted in the inventory or alias database.

```bash
gflow project get-media --media-id MEDIA_UUID --project PROJECT_UUID --profile pro2 --json
gflow project download-media --media-id MEDIA_UUID --project PROJECT_UUID --profile pro2 --output-dir ./out --json
```

REST `GET /v1/google-flow/assets/MEDIA_UUID?source=google&email=ACCOUNT&projectId=PROJECT_UUID`
returns a fresh confidential URL with no-store. Add `raw=true` to receive validated
PNG/JPEG/MP4 bytes. Images are bounded32MiB and decoded against fresh dimensions;
videos are bounded256MiB and validated with ffprobe. Generated-video URL
metadata can have null dimensions; downloads return positive dimensions measured
by ffprobe and compare any available fresh size with the content. Responses preserve their
validated MIME. Temporary downloads are removed on completion, invalid Range,
send failure or cancellation. No generation or upscale runs during these reads.

The REST media discovery worker now reuses the typed snapshot parser, so measured
uploaded/generated types and dimensions are no longer discarded by the timeline
adapter. Original timeline fields remain, and foreign attachments retain their
origin project. Sparse/unknown rows do not acquire an invented type or URL.
See the [focused R02 evidence and limitations](PARITY.md#r02-focused-delivery--4-october-2026).


Exact locally registered image/video aliases can replace MEDIA_UUID in these
read commands and SDK/direct MCP lookup/download calls. Run on the host holding
the private registration, with GFLOW_SELFHOST_ROOT pointing to the same root as
REST, and explicitly select the enabled owning profile and project. Registration
never proves current Google ownership: each read fetches fresh native detail and
checks the registered kind. Unknown UseAPI references refuse with an explanation;
opaque prefixes are never decoded or used to select an account. SDK/CLI/MCP
mutation and generation inputs remain raw. Character show and saved voice detail
have the corresponding read-only registered resource lookup, with fresh image
count and voice workflow checks.


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
