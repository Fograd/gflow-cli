# Predict: R10 original-profile session management

Verdict: CAUTION; five independent persona reviews, 8/10 each. Reuse the existing
persistent client, profile lease, private marker, native GetPeople helper, worker
queue and idle scheduler. No resident browser or new authentication transport.

Architect: retain an exact registration epoch and atomically record observations.
Security: pin the original expected principal privately; never compare Google email
to a public account alias, adopt a changed marker, parse error text or expose secrets.
Performance: bounded identity reads share one context; retain the cleanup allowance
and an indexed summary rather than historical scans on every GET.
UX: distinguish attestation, actual access, fresh principal, unknown and stale state.
Devil's advocate: duplicate completion must not extend backoff; mapping reversions
must not resurrect old success. Cookie housekeeping does not establish renewal.

Mitigations: epoch captured at admission and checked before execution/completion;
principal digest pinned once; fresh singleton principal on both sides of the project
read; only exact native identity HTTP401/correlated UNAUTHENTICATED or existing typed
auth errors indicate login required. Generic403, network and timeout remain unknown.
Timestamp validation uses the claimed job's execution interval. Legacy identity proof
is false. Manual observations participate in existing maintenance backoff.

Supported scope is original pro2/pro3 only. Pro1 is disabled and UseAPI-only.
Successful import and three-account live acceptance are excluded by operator policy.
Automatic renewal acceptance remains pending an observed supported renewal boundary.
