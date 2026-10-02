# Image download recovery

Confirmed reproduction: first image registers successfully, second missing path raises,
job has no media/checkpoint. CLI and seeded worker emit results only after all downloads.

Predict: CAUTION. Architect: shared helper for CLI and worker, no generation retry.
Security: private atomic invocation-scoped journal; bounded safe handles and contained
relative file paths only, no signed URLs, prompts, tokens or credentials. Performance:
max four records and 64 KiB journal; one fsync per completed output. Debugger: record
native handles before the first download, recover even if subprocess dies. Maintainer:
REST startup and runtime failure use the same reader and preserve existing video checkpoints.

Scenarios: second download fails; second file missing/oversize; later malformed record;
worker timeout/cancellation; daemon crashes after first download; stale invocation or
symlink journal cannot be imported; paths outside managed output cannot be imported.

- [x] Failing offline tests for native handles and first download surviving failure.
- [x] Shared atomic private journal and structured CLI partial download error.
- [x] Wire normal CLI and seeded/token worker download loops.
- [x] REST imports on failure/timeout/startup and checkpoints per returned output.
- [x] Fault and containment tests, focused CLI/worker/REST regression and type gates.

No browser or new generation required for this download-only reliability fix.


Sibling caller sweep: worker/daemon.py uses the helper plus additive optional checkpoint
imageRecovery/imageJournal fields (schema_version1 remains compatible). Startup uses the
exact journal reference; known handles survive even if a crash precedes the next DB
write. Both image_batch.py download paths use the helper; failed row outcomes retain
native images and completed files. The isolated legacy SDK generate_character portrait
download is a separate single-image character result path and remains with the root
character work owner.

Cross-platform review: no-follow and directory-fsync are capability-gated; lstat/fstat
identity checks and symlink refusal apply on the portable reader. A private child
directory scopes Windows ACL changes to journals, preserving user output permissions.

Verification: 164 worker/queue/batch/recovery tests passed; 85 CLI/seed/CAPTCHA/recovery
checks passed before the sibling expansion; latest 49 worker/recovery tests pass.
Focused Ruff and strict Pyright are green. Parent runs whole-repository gates after
all agents freeze source. No live generation or provider solve was performed.


Final snapshot: 296 focused CLI/API-seed/MCP-seed/REST/worker/queue/batch tests pass
in 18.06 seconds. Empty-workflow images download without fabricated workflow IDs.
Initial write/fsync and initial checkpoint callback faults return typed nonretryable
safe in-memory handles; completed files remain in that error even if a later journal
fsync fails. REST imports only bounded UUID handles and contained completed files
from those error envelopes, discarding all raw error text. Affected Ruff/format,
strict Pyright and all-document links (218 files) pass. Source handed back to parent
for final whole-repository gates; no commits or generation tests in this task.


Callback reliability follow-up (authorised ironclad API scope): cause proven at
runtime.deliver_callbacks: AsyncClient.post buffers the recipient response although
only status is used. The native Flow spike/debug gate does not apply to this local
HTTP-client behavior. Real HTTPX MockTransport tests failed first because the response
stream was iterated for 200, 500 and 302. Switching to AsyncClient.stream closes the
stream without body iteration, preserving exact host allowlist, global address DNS
pinning, Host/SNI, no redirects, timeout10 and five-attempt callback delivery.
