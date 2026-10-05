# R10 original-profile session management implementation plan

Goal: dependable, reviewable original pro2/pro3 session reuse with truthful private
status, bounded checks and clear original-profile recovery. User authorized completion,
publication to three aligned branches, production deployment and localhost checks.

Architecture: extend the existing selfhost health worker and queue. A compact private
registration-epoch summary retains dated access/identity proof, independently of
registration attestation and scheduler status. Browser ownership and storage stay in
the existing persistent client and profile lease. No speculative refresh mechanism.

Predict: CAUTION, mitigations recorded in PREDICT.md. Tests and live binding are in
SCENARIO.md. New queue schema6 retains history and private state. Older schema5 binaries
refuse it; immediate rollback uses maintenance interval0 on the current revision.

## Task 1 — Evidence and regressions
- [x] Verify clean baseline and publication pointers; read dated health evidence.
- [x] Bounded original pro2/pro3 principal/project cold opens and memory measurements.
- [x] Reproduce missing principal/status/backoff behavior before fixing.

## Task 2 — Focused implementation
- [x] Fresh expected Google identity before and after native project health reads.
- [x] Exact401/UNAUTHENTICATED distinction, safe legacy identity projection.
- [x] Admission-pinned epoch/principal digest and completion revalidation.
- [x] Indexed private last access/identity/latest status and local freshness policy.
- [x] Reuse maintenance with newer manual observation backoff and no duplicate renewal.

## Task 3 — Acceptance and delivery
- [x] Focused controlled tests and original-profile live BDD checks pass.
- [x] Update session/operations/parity/verification docs and changelog.
- [x] Required repository checks and independent review.
- [ ] Atomic publication to develop and both requested feature branches.
- [ ] Guarded production deployment, idle service restart and Mac localhost queued proof.
- [ ] R10_HANDOFF.md, read-only R10_CHECK.py and brief OVERNIGHT.md entry.

This is the pre-publication plan snapshot; final delivery checks are recorded in the
operator R10_HANDOFF.md after publication and production acceptance.

## Pending renewal acceptance
- [ ] Observe a supported automatic authentication renewal boundary without human login.

This last checkbox stays open if not observed. Periodic access, cookie changes and
successful health checks cannot discharge it. Import and three-account acceptance
remain excluded; no paid calls, profile replacement or pro1 access is authorized.
