# Accepted cookie refresh scope preservation
Predict: CAUTION8/10. Existing staged identity/project verification is source-backed; no
new Google request or scheduled renewal is introduced. Keep immutable profile origins while
resolving accepted same-account refresh lineage. Use one jobs database transaction; WAL
ATTACH cannot give multi-file crash atomicity. Account removal invalidates lineage.

- [x] Red tests: accepted/repeated refresh, immutable job audit/statistics, aliases, transaction
  rollback, historical profile reuse, account delete/re-register and update timestamp.
- [x] Private account_profile_lineage with atomic activation and tombstone invalidation.
- [x] Optional registry scope resolver plus HTTP exact active-account validation.
- [x] Statistics resolves historical immutable profiles through accepted lineage.
- [x] Bounded private confirmed-receipt carryforward and activation-failure cleanup.
- [x] Exact idempotency replay under proven lineage; changed payload/unrelated registration refuses.
- [x] Focused gates:200 tests, lint/format/type/diff clean.
- [ ] Parent independent review/live read acceptance. No automatic login-refresh claim.
