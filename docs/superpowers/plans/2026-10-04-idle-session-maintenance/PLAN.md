# Idle Session Maintenance Implementation Plan

Goal: optional ordinary native project-access checks for idle enabled profiles, without repeated cookie transfer or claims of authentication renewal.

Architecture: settings default zero; one daemon task queues existing accounts/health jobs using atomic SQLite admission and a small registration-scoped scheduler pointer. Existing serial workers and ProfileLease execute the bounded native read. Safe account metadata exposes schedule status separately from attestation.

Predict verdict: CAUTION, 7.6/10. Parent approved bounded implementation; no full gate, commit, deployment or Google calls in this worktree.

- [x] Add red offline tests and Gherkin for due/idle/once, disabled, backoff, restart, stale scope, cancel and privacy.
- [x] Add validated interval, atomic persisted admission/status and queued-only cancellation.
- [x] Wire lifespan scheduler and pre-subprocess scope/config guard.
- [x] Document operator enable/stop, queue delay, profile retention and unverified renewal; mirror env templates.
- [x] Run focused clean-env pytest/lint/types; obtain independent review and hand off for parent integration/full gate/live coordination.

No CLI or MCP command is added. Existing direct/queued clients still coordinate through ProfileLease. Renewal-boundary acceptance remains open.

## Focused handoff verification

- Baseline session health: 19 passed.
- Red scaffold: 34 missing-feature failures; three Gherkin failures before production implementation.
- Adversarial mapping reversion: two RED failures, corrected by exact persisted scheduler-job joins.
- Final clean-environment affected run: 178 passed in 10.71s, including 41 maintenance cases, three BDD scenarios, health/account/import/HTTP semantics and binding guard coverage. Six existing pytest-bdd/Pytest deprecation warnings.
- Changed source/tests ruff check and format pass; scoped pyright with the shared venv interpreter: zero errors/warnings.
- Document links: all resolved across 233 files; git diff whitespace check passes.
- Independent review: GO, no source blocker. Schema5 rollback and enabled lifespan notes incorporated.

Parent still owns full gate, integration/publish and coordinated actual scheduled native health smoke. No live Google, profile lease, solver, generation, service changes or commit were performed in this isolated worktree. R10 automatic authentication renewal and idle/renewal-boundary acceptance remain open.
