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
