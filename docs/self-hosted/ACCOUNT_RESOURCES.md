# Observed account characters and saved voices

This fork extension reads native project catalogs across the selected account and
returns observed characters or saved user voices. It makes no generation or
deletion request. It does not claim a complete account inventory. System presets
are available separately through the existing voice catalog.

## Interfaces

SDK:

```python
page = await client.list_account_resources(
    kind="character", max_projects=10, max_pages=1, max_seconds=180
)
while page["next_cursor"] is not None:
    page = await client.list_account_resources(
        kind="character", cursor=page["next_cursor"],
        max_projects=10, max_pages=1, max_seconds=180
    )
```

CLI: `gflow project account-resources --kind character --profile NAME --json`.
The existing `gflow project resources` spelling remains a compatible alias.
Pass `--kind voice` for saved voices, `--cursor TOKEN` to continue,
`--max-projects`, `--max-pages`, and `--max-seconds` for bounds.
Direct registered MCP: `gflow_list_account_resources(kind, profile="default",
cursor=None, max_projects=10, max_pages=1, max_seconds=180)`.
These reads run directly; there is no queued generation twin.

HTTP: authenticated
`GET /v1/google-flow/assets/resources/{email}?kind=character&maxProjects=10&maxPages=1&maxSeconds=180`.
The path uses the registered public account handle. Optional `cursor` is the
opaque continuation from this endpoint. Only the documented query fields are
accepted; duplicate fields and unrelated project/source/async controls refuse.
The HTTP worker runs synchronously with the requested read budget plus bounded
startup/cleanup time. Worker failure returns502 with committed progress retained.

## Bounds and continuation

`max_projects` / `maxProjects`: integer1–20 per call; default10.
`max_pages` / `maxPages`: integer1–100 discovery pages; default1.
`max_seconds` / `maxSeconds`: integer1–180; default180.
Each result contains at most1000 resources. Pending committed result rows are
drained before additional native reads. Repeated calls can therefore return
another result page with zero new catalog reads.

Omitting the cursor starts a fresh read epoch. A continuation belongs to the exact
physical profile, configured Google principal, kind and active epoch. It cannot
be reused across accounts, kinds, a replaced profile, or a new epoch. Concurrent
writers and stale continuations refuse instead of merging uncorrelated progress.
Google's raw pagination cursor is stored only in the private checkpoint.

Rows contain `kind`, `native_id`, `origin_project_id` and
`observed_in_project_ids`, plus `workflow_ids` for a character or
`workflow_id` for a saved voice. A saved voice requires an actual visible saved
user TTS resource; an attached generic audio asset is not counted as a voice.
This listing does not expose playback URLs, captions, dialogue, personality,
display names or authentication material. Fresh detail/playback reads remain
separate existing interfaces.

## Meaning of results

`returned_count` counts this page; `observed_count` counts the current epoch.
`pending_result_count` and `pending_project_count` distinguish unread committed
rows from discovered catalogs still to visit. Per-call and cumulative page/catalog
counts report actual reads. `timed_out` preserves successful prior commits.
`next_cursor` and `truncated` indicate more pending results or traversal.
`traversal_finished` means observed discovery pagination and pending catalogs
were exhausted; it can be true while pending result rows still have a cursor.

`complete` is always null and `deletion_authority` always false. Catalog visibility
and account pagination do not establish global completeness, a consistent
point-in-time snapshot, attachment in another project, or permission to delete
absent resources. Previous observations remain private across epochs and are
not presented as fresh results.

Storage is a private0700 directory and0600 `account_resources.sqlite3` beneath
the configured native inventory home. Atomic checkpoints retain allowlisted
identity/workflow metadata; URLs and user text are excluded. This extension is
separate from [inventory synchronization](NATIVE_INVENTORY_SYNC.md), which also
tracks media and generated history.

HTTP binds the selected registered profile to the exact private recorded principal digest before worker dispatch and rechecks registration and principal before publication. The worker retains that binding across browser opening and before every commit. This is a recorded-principal consistency check; it does not claim a new Google identity attestation. Operator account handles may differ from private Google emails.

R03 synchronization and this listing now reuse the same private recorded-principal
checks. The scoped SDK sync method is `client.sync_native_inventory(...)`; sync
counts also include media/history and retain previous observations across fresh
scans. This listing returns only its current epoch's character or saved-user-voice
rows and its opaque continuation, so its counts can legitimately differ from
retained sync counts. Exact eight-slot empty-project catalogs are accepted as
observations with unknown completeness; malformed or unrelated replies still refuse.
See [synchronization progress](NATIVE_INVENTORY_SYNC.md#r03-supported-traversal-and-progress).
