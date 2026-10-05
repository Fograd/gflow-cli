# Resumable native inventory synchronization

Run `gflow project sync --profile NAME --max-steps 10 --max-seconds 180 --json`.
Repeat the same command to resume. The direct MCP twin is
`gflow_sync_native_inventory(profile, max_steps=10, max_seconds=180, restart=False)`.
A saved configured account identity is required before opening the browser.

Each step reads one account project page, one project's media/workflow/character/saved-user-voice
catalog, or one native account-history page through existing native SDK reads.
Discovered projects are cataloged before continuing account pagination. History-only projects
also receive catalog reads. Each verified read commits allowlisted observations and its checkpoint
in one SQLite transaction. Failed or interrupted reads resume at the last committed checkpoint.
Concurrent checkpoint writers refuse stale updates; retry the synchronization command.

Controls: 1–100 steps and 1–300 seconds per run. `--restart` starts a fresh traversal while
retaining previous observations. Completed traversals do no reads until restarted.
`traversal_finished` means that the observed pagination and pending catalogs were exhausted;
every resource's `complete` remains null. No absence implies deletion, ghosting, ownership,
or complete account history. A traversal is not a consistent point-in-time snapshot.

Storage is `<configured GFLOW_CLI_HOME>/native_inventory/native_inventory_sync.sqlite3` with
a private directory/file (0700/0600). Checkpoints and observations are scoped by profile and
a hash of configured account identity. Pagination cursors remain only in private checkpoints.
Stored resource metadata excludes URLs, names, prompts, dialogue and authentication tokens.
Discovery, project-catalog and native-history observations have distinct scopes; catalog attached
media retains its origin project and explicit attachment relationship.

The service hook `services.inventory_sync.sync_native_inventory` supports the self-hosted
worker's configured private root and exact account/profile selection. CLI and direct MCP run these
credit-free reads directly; they do not enter the generation task queue. Live acceptance belongs
to the authenticated read-only BDD gate, not to offline orchestration tests.


## Self-hosted HTTP
POST /v1/google-flow/assets/sync/{email} is a fork extension. Send bearer
authentication and JSON {"maxSteps":10,"maxSeconds":180,"restart":false}.
The path uses the configured public account handle. Unknown fields or invalid
bounds refuse before a worker starts. It shares the private checkpoint with CLI
and direct MCP. Worker failure preserves committed progress; repeat to resume.
No generation job is created.

A real authenticated SDK BDD on 4 October performed two one-step calls sharing
a checkpoint: the second advanced the version and committed a project catalog.
Metadata remained URL-free, completeness null, and zero generation RPCs were sent.
This establishes resume, not complete account visibility.

## R03 supported traversal and progress

Prefer the scoped SDK entry point, which derives the profile and recorded principal
from the client's private configuration and rechecks it before reads, commits and
publication:

```python
async with FlowApiClient(profile_dir=settings.profile_subdir("authorised-profile")) as client:
    progress = await client.sync_native_inventory(max_steps=10, max_seconds=180)
    # Repeat until progress["traversal_finished"], or explicitly restart a fresh scan.
```

CLI, direct MCP and REST use that same method and private checkpoint. CLI/MCP check
the recorded principal before and after browser opening. REST captures the exact
registered profile/principal before dispatch and checks it again before returning.
A changed or missing principal refuses; this consistency check is not a new Google
identity attestation. Use an explicitly authorised profile or registered REST handle.

`steps_read` counts successful reads in this call. `checkpoint_version` advances
only on committed work, including an explicit restart. `scan_id` changes on restart.
`project_pages_read`, `history_pages_read`, and `catalog_projects_read` describe the
current traversal. Legacy checkpoints start the new page counters at zero on upgrade and increment
them during resumed reads; earlier reads are not backfilled. They retain their
previous progress and observations.

`observations` retains the existing per-scope counts across scans.
`retained_unique_counts` counts distinct native identities per resource kind across
all scopes and retained scans; do not add scope counts to infer unique resources.
These are observations, not a claim that old rows were visible in this scan.
`pending_project_count` and the two pagination flags distinguish pending catalogs
from additional discovery/history pages. `traversal_finished` requires both observed
pagination streams and all pending catalogs to finish. `complete` remains null and
`deletion_authority` false, including after traversal finishes.

Media keeps its original `project_id`, `workflow_id`, and the union of observed
`attached_to_project_ids`. The legacy singular `attached_to_project_id` records the
most recently observed attachment; use the plural list for retained relationships.
Character `workflow_ids` also retain the union of previously observed references.
No absent row or absent relationship automatically deletes anything.

Catalog reads accept the measured eight-slot empty-project response with null
project/timeline/media collections only when the native request is successful and
correlated to the exact selected project. Normalisation applies only to catalog
observations; strict ownership and mutation readers retain their existing rules.
Unknown or mixed response shapes refuse and leave the catalog pending.

A failed read preserves earlier commits. A Google-invalidated cursor or unsupported
catalog remains an explicit error, not traversal completion. If a fresh scan is
needed, use `--restart` / `restart=true`; previously retained observations survive.
Google's catalog/history visibility does not establish every historical, hidden,
shared, deleted or otherwise inaccessible resource, or a point-in-time snapshot.
