# Scenario: R10 session identity, persistence and private status

Active dimensions: auth lifetime (D1), WAF/error distinction (D2,D7,D9), ownership/
teardown (D5), durable epoch/timestamps (D6), path privacy (D8), headed cold reopen
(D10), validated inputs (D11), private observations (D12), REST versus MCP (D13).
No composer selector, generation, manifest or CAPTCHA token changes (D3,D4).

| Case | Expected result | Verification |
|---|---|---|
| Matching marker, wrong fresh Google principal | UNKNOWN/identity_changed before project read | Unit |
| Account changes during project read | UNKNOWN, no successful identity proof | Unit |
| Marker and principal change together | Pinned expected digest refuses | Unit |
| Exact identity HTTP401/correlated code16 | LOGIN_REQUIRED | Real classifier unit |
| Generic403/network/timeout/busy/close/cancel | UNKNOWN; preserve profile and cancellation | Focused existing tests |
| Old, future or malformed worker timestamp | No new verified access | Unit |
| Interrupted check after success | UNKNOWN latest, historical success retained | Store restart test |
| Mapping A to B to A during a check | Old epoch cannot update current status | Unit |
| New manual failure after maintenance OK | Backoff follows manual result | Unit |
| Duplicate terminal result | No status/backoff extension | Unit |
| Disabled pro1 | No scheduled read or profile/status probe | Unit and deployed |
| Independent queues | Original per-profile serialization, one global maintenance read | Existing race tests/deployed |
| Original cold reopen | Fresh same principal plus project access; no refresh claim | Tagged live BDD |
| Idle API/MCP restart | Fresh queued checks through Mac localhost | Deployment proof |

The real-browser scenario is bound once from tests/e2e/test_r10_session_health_bdd.py
using @e2e @e2e_auth; error/state machinery stays offline. Existing intercepted
login/challenge regressions and leases are reused. Google may request human login;
its renewal boundary has not been observed. No forced expiry or credential transfer.
