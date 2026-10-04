# Resumable native inventory synchronization

Goal: Resume bounded account discovery, per-project catalogs and native history after interruption.
Predict: CAUTION (8/10). Architect: isolated service reuses proven SDK reads. Security:
private storage, account/profile scoping and allowlisted metadata. Performance: serial bounded
reads avoid page-pool contention. UX: CLI and direct MCP share controls; REST worker hook is
root-owned. Devil's advocate: no transport, ownership authority or deletion sweep is needed.

- [x] Red tests: interruption/resume, empty resources, cap, cycle, privacy and scope isolation.
- [x] Service: atomic metadata/checkpoint transactions after each read, concurrent CAS guard.
- [x] CLI project sync and direct MCP mirror; these credit-free reads have no generation queue.
- [x] Focused tests, Ruff and strict Pyright.
- [ ] Root: live read BDD, REST worker/server integration, full gate and documentation consolidation.

Pagination exhaustion reports only traversal progress; every resource completeness stays unknown.
A restart begins a new traversal while retaining observed rows; omissions never remove resources.
