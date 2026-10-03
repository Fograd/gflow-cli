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

SDK delete_native_media and CLI project delete-media permanently target only requested owned identities. Every present ID passes a fresh GetMedia ownership/type check before at most one BatchDeleteAssets request. A missing ID requires the confirmed deletion receipt described below. The payload contains media IDs and no workflow IDs; unrequested siblings are not included. Explicit true confirmation and 1–100 distinct UUIDs are required. UUID aliases are normalized before duplicate checks.

~~~bash
gflow project delete-media --project PROJECT_UUID --media-id MEDIA_UUID --confirm-delete --profile PROFILE --json
~~~

NativeMediaMutationUnknownError operation delete preserves pending IDs after an unconfirmed response. Never replay automatically. Reversible whole-batch archive remains separate. The media-only wire is derived from the deployed frontend source. One final owned synthetic clip received an empty acknowledgement, remained in an immediate project read, then disappeared from a fresh project timeline; exact GetMedia subsequently returned native not-found (gRPC 5) with no owned media reply. This proves deletion of that acknowledged fixture, with delayed read visibility. It does not establish a guaranteed visibility interval, all media types or preservation of every possible sibling structure. The final separately authorized synthetic upload/delete lifecycle with bounded read-only polling passed: one test passed and four skipped in 28.91 seconds, with every originally active media identity preserved.

Upload readiness is established by the native add-menu becoming visible; a hidden classic settings button alone does not show that native upload is unavailable. The corrected readiness check reached the upload menu in the final synthetic fixture run.

## Confirmed deletion retries (R09)

The fork records each strictly acknowledged permanent deletion in private profile metadata, scoped to the freshly verified Google account, project, canonical media UUID and exclusive media type. A repeat request is accepted only when exact fresh GetMedia reports native NOT_FOUND (gRPC5) and a matching receipt exists. Unknown missing UUIDs, authorization errors, malformed responses and inventory absence refuse the whole batch before any write.

Fresh same-session identity must resolve uniquely on Google's account-index-zero page. The selected project must be positively found within two current account project-list pages; a truncated listing never proves deletion. Ambiguous identity, another account/project/profile or malformed/public/symlink receipt files refuse. Request preflight is bounded120seconds.

For mixed batches, only freshly present IDs enter one permanent deletion RPC. An all-confirmed-gone batch makes zero mutation calls. SDK/CLI/direct MCP preserve the requested `deleted` list and add `newly_deleted`, `already_deleted` and `receipt_persisted`. Self-hosted native-delete job responses preserve `deleted` and add `deletedCount`, `newlyDeleted`, `alreadyDeleted` and `receiptPersisted`. Counts include all validated requested IDs. Failed receipt persistence after Google's acknowledgment remains a known successful deletion with the persistence flag false; it does not authorize mutation replay.

This is narrower than [useAPI's already-gone contract](https://useapi.net/docs/api-google-flow-v1/delete-google-flow-assets-email): its identifiers encode ownership, whereas this fork's raw UUIDs do not. Media removed outside this fork or before receipt support cannot be accepted merely because it is absent. Native audio deletion is a fork extension; useAPI's media endpoint documents image/video only.

Free owned-synthetic batch/retry BDD passed1test,2warnings in43.96seconds: three uploads, two deletion writes, zero writes for the all-gone repeat, only the third UUID in the mixed-batch write, originals preserved. No generation or CAPTCHA task occurred. Final exact-envelope/account-index/page-readiness guard regressions are verified offline separately.


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
