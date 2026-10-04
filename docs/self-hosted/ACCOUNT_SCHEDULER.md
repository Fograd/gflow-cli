# Automatic account selection and local quota policy

Explicit `email` and owned-reference account pins keep that account. Unpinned
image/video requests use enabled, verified registrations and existing local
score/queue ordering. Metadata reads bypass cooldown filtering; the sole valid
account is retained, following the useapi compatibility exception.

Only an exactly correlated singleton native RPC with the expected gRPC code and
typed quota reason can update a cooldown. Terminal jobs retain safe native
reason, actual wire model key, operation and proof fields. Mixed/unknown replies,
late unrelated jobs and ordinary CAPTCHA refusals cannot create a cooldown.

| Observed native reason | Local policy |
|---|---|
| USER_QUOTA_REACHED / USER_REQUESTS_THROTTLED | Account-wide30minutes |
| PER_MODEL_DAILY_QUOTA_REACHED / UPGRADEABLE | Exact operation and observed wire model until nextUTCmidnight |
| MODEL_ACCESS_DENIED | Exact operation and observed wire model for1hour |
| UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC | Typed terminal refusal; no account/model cooldown |

These are `useapi-compatible-local-policy-v1` intervals, not observed Google
reset times. Exact-model filtering requires the actual wire key; a CLI/UI alias
does not imply that key. Global cooldowns still apply to automatic requests.
Duplicate terminal delivery does not extend a cooldown. Cookie refresh preserves
registration lineage; unrelated registrations do not inherit it.

If every automatic alternative is covered, HTTP returns flat429 with
`error:no_eligible_account`, `code:local_quota_policy`, `retryAfter`,
`retryAt`, `skipReasons`, `policy` and `resetSource`, plus `Retry-After`.
Explicitly pinned calls and reads keep their existing error contracts.

Deleting a registration preserves its browser directory and retained audit
scope. Reusing a deleted physical profile name is refused409. Register with a
fresh logical profile and fresh public account handle; retained registration
handles are unique. This prevents new jobs and aliases being mistaken for old
deleted scopes.

CAPTCHA outcomes remain separate: solver success is not Google acceptance.
See [CAPTCHA](CAPTCHA.md), [HTTP jobs](HTTP_JOB_SEMANTICS.md) and
[session import](COOKIE_IMPORT.md). Actual output checks belong to
[final E2E](FINAL_E2E.md).
