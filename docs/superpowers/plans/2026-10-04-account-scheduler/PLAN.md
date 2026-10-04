# Rolling-score account scheduler
Parent-approved design: automatic selection uses existing public combined rolling15min score, then created/running queue load and stable profile tie. Pinned accounts/owned references bypass. No new public fields, paid calls or tier/model assumptions.
Predict: GO8/10 for source-backed score reuse; quarantine STOP pending exact native reason/model durable mapper.

- [x] Test first score vs queue, combined families, exact weighted failure/rate limit, stale15min expiry.
- [x] Test pinned email/managed/native refs unchanged; mixed refs refuse before queue.
- [x] Test accepted refresh lineage + exact current configured profile; stale/disabled/unverified/no candidate refuse.
- [x] New account_scheduler selects exact current candidates using job_statistics summary.
- [x] Replace only automatic pick_account selection branch, map empty candidate to503.
- [x] Lint/format/types/affected tests (188 passed); root owns public docs and full integration.

No live Google surface changed: this selects a local queue profile before existing worker ownership/entitlement checks; offline HTTP tests assert durable routing. Root sole authorized live caller. Official hosted random tie is replaced by approved deterministic queue tie extension.
