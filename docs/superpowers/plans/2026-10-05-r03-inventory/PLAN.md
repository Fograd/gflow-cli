# R03 inventory delivery

**Goal:** Finish supported, resumable inventory traversal for an explicitly selected authorised account, publish aligned fork branches, deploy and verify through Mac localhost.

**Architecture:** Reuse native project/catalog/history reads, SQLite checkpoints and account-resource principal binding. Preserve observed relationships by union; keep retained counts distinct from current traversal. No generation, voice creation, profile replacement or absence-based deletion.

**Predict verdict:** GO. Architecture/performance/minimality reviewed inline; independent security and interface review GO 8/10. No new Google wire, browser authentication policy, queue or database table.

## Checklist

- [x] Confirm clean development/production/mirror and three fork branches at the supplied revision; read R02 handoff, operations and R03 docs.
- [x] Identify existing bounded reads, atomic resumable checkpoints, fresh-scan retention and account-resource continuation.
- [x] Add controlled regressions for attachment/workflow retention, unique counts, old checkpoints and principal changes.
- [x] Preserve attachment/workflow identity unions and expose scan/version/page progress and retained unique counts.
- [x] Add scoped SDK sync method and reuse it from CLI, direct MCP and REST worker, with dispatch/browser/commit/publication principal checks.
- [x] Verify live traversal completion, bounded resume, retained fresh scan and known existing resources on original pro2/pro3.
- [x] Run tagged read-only BDD; review code/docs and mirrors.
- [x] Run repository gates before publication; one unchanged parallel picker fixture passed isolated recheck.
- [x] Replace current R03 status with supported scope, actual evidence and exact visibility/fixture limits.
- [ ] Commit and atomically publish develop and both feature branches; deploy the tested revision after jobs drain.
- [ ] Verify actual deployed REST/MCP through Mac localhost; finish Mac R03 handoff and overnight checkpoint.

## Risks and mitigations

- A Google-invalidated cursor or unreadable catalog must fail or remain pending. Use an explicit fresh scan to recover; retain previous observations.
- Retained observations are not a fresh snapshot or ownership/deletion authority. Completeness stays null.
- Legacy checkpoints acquire stable scan identifiers and default new counters without deleting rows or changing Google profiles.
- Account registrations/recorded principals are rechecked using the existing account-resource implementation. This is not a new Google identity attestation.
- Initially all discovered catalogs had zero characters. The user then explicitly authorized use of their opened Flow tab to resolve this gap. A temporary metadata-only character from an existing image supplies live discovery evidence; clean up only that fixture and retain original assets. No generation is authorized or needed.

## Evidence checkpoint

SDK pro2 completed 3 catalogs/31 history pages; tagged pro3 E2E passed both resume and completion/fresh-retention scenarios across 10 catalogs/50 history pages. Existing generated/uploaded media and saved voice positively matched. The user-authorized temporary existing-image character was discovered by SDK/catalog/sync/account resources and actual CLI. No generation or paid solver requests. Private Mac `R03_HANDOFF.md` records publication/deployment and fixture lifecycle after delivery. Documentation council: GO after legacy-counter wording and generated mirror refresh. Shared adapter-session extraction reviewed GO and focused 38 tests passed.

Whole-tree hygiene, doc links, published PII/mirror, council memory, ruff lint/format and strict types passed. Full suite: 7988 passed, 5 skipped, 89.87% coverage; one unchanged virtualized-picker fixture failed under parallel load, then its entire file passed 3/3 with one worker and a separate basetemp. This test fragility is recorded rather than changing unrelated picker behavior. R03 focused regressions and tagged live E2E passed. Duplication proxy has only pre-existing findings after shared adapter extraction.
