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
