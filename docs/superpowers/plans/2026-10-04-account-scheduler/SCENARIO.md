# Scenario: rolling-score automatic account scheduler
D4/D5/D6/D7/D11 active: routing continuity, queued ties, SQL rolling windows, no eligible candidate; D13 mirror: REST-only local multi-account queue policy, CLI/direct MCP continue explicit profile selection. Auth/transport/selectors/token/OS paths untouched.

| Case | Severity | Expected behavior |
|---|---|---|
| Recent failed or429 account vs idle account | High | Exact existing10/20 score penalty; no quarantine guess |
| Recent completion vs queued load | High | Score primary; queue secondary |
| Last15min terminal window expires | High | Fresh selection reflects expiration, no sticky cached score |
| Original immutable jobprofile after accepted refresh | High | Current publichandle score includes committed lineage |
| Explicit email or managed/native ownedrefs | Critical | Exact selected/owner profile bypasses automatic reroute |
| Mixed profile refs | Critical | Refuse422, no job |
| Stale config profile with matching handle | High | Refuse automatic adoption unless current exact registration matches |
| Disabled/unverified/allunavailable | High | Exclude; no candidate503 before queue |

Quarantine unavailable mapper: only exact unusual-activity/content typed refusals presently persist; generic rate-limit exit4 is insufficient to distinguish modeldaily, accountquota or requestthrottle cooldown. Never infer cooldown from free detail text/all429 or invent tierstate.
