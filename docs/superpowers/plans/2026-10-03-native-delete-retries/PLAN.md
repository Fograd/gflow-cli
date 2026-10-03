# R09 confirmed deletion retries
Goal: safely accept repeats of this fork's acknowledged permanent deletions, without claiming ownership of arbitrary absent UUIDs.
Predict: Architect/Security/UX CAUTION8 mitigated by fresh exact account identity, profile-private account/project/type-scoped receipts, positive current project membership, exact NOT_FOUND and known-ack persistence failures. Performance GO8: one page lease, bounded reads, zero replay of missing IDs. Root Devil GO8: narrow idempotency rather than undocumented resubmission of missing UUIDs.
- [x] Red tests for exact RPC missing classification, receipt scope, all-gone zero writes, mixed present subset and whole-batch refusal.
- [x] Implement strict native read errors, private scoped receipts and one bounded deletion preflight.
- [x] Preserve CLI/MCP deleted lists; add REST deletedCount and separate already-deleted IDs.
- [x] Free owned synthetic batch/retry BDD; no original deletion or paid generation.
- [x] Docs and six mirrors, full gates/council:6337pass/89%, final GO.
- [ ] Publish and idledeploy.
Arbitrary IDs already removed outside this fork remain unprovable, not parity-complete. Never infer absence from truncated inventories.
