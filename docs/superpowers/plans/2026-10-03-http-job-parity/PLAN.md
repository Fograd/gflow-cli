# HTTP job response parity

Goal: implement useapi sync/async response semantics without cancelling or replaying durable generation jobs. Scope is the self-hosted HTTP adapter; CLI/MCP generation contracts and Google transport remain unchanged.

## Predict

CAUTION, confidence 8/10. Independent security/performance assessment (upscale): whitelist public nested fields; never expose token/secret paths/raw worker output; bounded monotonic waiting must leave worker ownership intact. Independent UX/devil's-advocate assessment (parity): retain camelcase jobId alias, preserve unknown outcomes and partial outputs, callback/polling must share one projector, and timeout must instruct polling. Architect: separate enqueue from HTTP delivery and public projection from internal SQLite state. No new compatibility flag.

## Authoritative contracts

Reviewed official [video generation](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos), [video upscale](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-upscale), [job lookup](https://useapi.net/docs/api-google-flow-v1/get-google-flow-jobs-jobid), and [concatenate](https://useapi.net/docs/api-google-flow-v1/post-google-flow-videos-concatenate) documentation on 2026-10-03. Advertised async video responses are 201; successful sync results 200; video polling timeout 408 after 600 seconds, concatenation after 180 seconds. Image async is an existing self-hosted extension, not an upstream parity claim. Native operations may lack upstream operation handles: never fabricate them.

## Critical/high scenarios and tasks

- [x] Red tests: async 201 and Location; sync 200 only on completion; failed sync non-200; deadline 408 retains exactly one queued job.
- [x] Add a pure safe HTTP projector with ISO dates, lowercase jobid plus jobId alias, started projection, interrupted as failed/outcomeUnknown; preserve verified partial handles and protected download paths.
- [x] Share projector between GET jobs and durable callback snapshots; preserve replyRef, reject malformed replyRef before enqueue, omit token/secret/absolute paths and unknown nested worker fields.
- [x] Separate enqueue from response delivery; same idempotency key may switch response mode without adding a job, cancelling a wait never cancels a durable worker.
- [x] Validate finite wait budget, endpoint bounds, and map only typed CLI exit codes to documented HTTP failures with safe fallback.
- [x] Test success/failure/unknown callback equality against polling, legacy records, restart, partial output preservation, and nested secret redaction.
- [x] Update HTTP semantics guide and affected existing tests intentionally; run complete selfhost suite, Ruff, format, Pyright and doc-link checks. Root runs full repository gates before commit.

No browser or paid generation is necessary for these HTTP-local contracts. Existing browser failures remain typed, non-replayed outcomes. Documentation must explain that sync 408 is an HTTP wait expiry and work can continue; clients poll the same job rather than resubmitting.

## Execution evidence

Initial eight HTTP contract tests failed on the old implementation, then passed after projection and response separation. Expanded selfhost suite: 291 passed with Auto integration. Root authorized the labeled shared Auto resolver; REST validates owner/project/path and preserves policy metadata without modifying Google transport. Pending legacy callbacks retain their event state when upgraded. Canonical response.media avoids duplicating binary payloads. No paid work or browser operations performed.


## Final HTTP-local verification

The cookie activation follow-up extends the same daemon boundary: account schema
v3 retains creation time and verification source; cookie refresh atomically maps
the same proven principal to a new owned profile while transferring managed
asset ownership and preserving historical jobs. Both profile leases and the
accepted-job guard apply before activation; candidates whose ownership changed
are retained with safe cleanup feedback. Bounded account-marker reads reject
symlink, inode and in-place size/mtime races and complete short reads.

Final focused gates on 2026-10-03: 339 tests passed (complete selfhost suite plus
HTTP job and cookie-table local BDD), affected Ruff clean, affected strict
Pyright zero errors. No browser or provider work was performed by this agent.
Root retains repository-wide gates and publication ownership. Successful live
cookie transfer remains unverified; safe authentication rejection is documented.
