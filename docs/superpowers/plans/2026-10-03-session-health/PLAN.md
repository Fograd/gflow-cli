# On-demand actual project access health

Purpose: distinguish historical operator registration flags from a recent actual
Flow project access check, without promising that verification keeps a Google
session alive or establishes the cause of a prior sign-out.

Current evidence: the user completed human login and root verified real native
project access. The earlier public /about landing is consistent with the known
additional identity challenge in KNOWN_ISSUES #902/#888; it does not prove that
cookie expiry, copying, or any particular automation call caused the incident.

Predict: Security and Devil CAUTION8 (root independent assessment): bearer-only
selected registration, no user-selected paths/project replacement, bounded
native read, no secrets/raw exceptions, no scheduling/refresh/cookie mutation,
no transient-failure downgrade. Architect/Performance GO with cautions (upscale independent assessment): one
overall finite probe plus existing bounded cleanup, actual lease ownership, no
concurrent acceptance races or refresh loops. UX/Crossplatform GO with conditions
(parity independent assessment): timestamped scoped evidence, unknown distinct
from explicit authentication failure, no registration flag mutation. API hook is gated on their handoff and serialization
strategy: an idle check alone races concurrent generation acceptance. Reuse the
existing per-profile queue for a read-only health job or explicitly reserve the
profile before accepting a health action; never nest ProfileLease around a client
that owns its own lease.

Implementation scope: new pure session-health module and fake-browser teardown
regression tests. HTTP server edits wait for image-marker ownership release and
root's queue-boundary decision. CLI/MCP have auth-status/catalog-read paths; no
new secret-taking surface or generated job behavior is added by this helper.
Any eventual HTTP route must document its self-hosted extension status.

Tasks:
- [x] Verify three cookie council fixes: FIFO refused before open; candidate ACL
  hardening inside cleanup try; fingerprint/identity captured before rename.
- [x] Add fake context tests for population cancellation, context close failure
  and fallback, cancellation during close, driver exit and lease release.
- [x] Implement safe fixed status projection for one bounded actual project read;
  identity marker validated and rechecked, no persistence/auth mutation.
- [x] Test busy/missing-marker/invalid-registration refusal before client creation,
  success only after actual read, timeout/transient/auth/close errors, cancellation.
- [x] Integrate the serial HTTP worker, update account-health docs, and pass local gates.
  Exclusive live helper and isolated real HTTP queue checks passed after login.

No paid generation/provider task and no copied production cookies.


## Execution and remaining gate

Root selected the existing serial durable worker, resolving the acceptance race.
The authenticated HTTP action pins the registered profile/project and queues a
read-only health kind. The native worker emits only fixed public observation
fields; public polling/callbacks share a whitelist. Interrupted health reads
finish unknown rather than a billable submission error. No authentication flags
or cookies are mutated. Root owns the exclusive live endpoint proof and full
repository publication gates; no live browser/provider operation was performed
by this agent. Complete selfhost plus HTTP/cookie local BDD: 381 passed; affected
Ruff and strict Pyright clean. The coordinator subsequently verified the real health helper and an isolated HTTP queue: unauthenticated401, async201, completed OK/project_access_verified. Production deployment smoke remains separate.

Separately, typed image submission uncertainty now survives CLI→runtime→queue→
HTTP with exact class/type/exit/project contract validation, safe bounded UUID
handles, phase and nonretryable unknown flag. The checkpoint merges earlier
verified media and downloads instead of discarding them. Negative contract and
secret-redaction tests passed, without any Google submission.

Published/deployed fd56b2e6. Production HTTP queue passed401/201/completedOK/project_access_verified and the registered MCP schema read passed. No generation, refresh or solver.
