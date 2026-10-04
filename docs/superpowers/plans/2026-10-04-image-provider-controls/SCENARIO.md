# Image provider scenarios

| Dimension | Severity | Required behavior |
|---|---|---|
| Auth/session | Critical | Exact HTTPS Flow project before and after solving; navigation refuses |
| WAF | Critical | Only same dispatched request typed unusual-activity refusal can retry; fresh override/token each attempt |
| Selectors/locale | Low | No selectors changed |
| Batch/resume | Critical | Count matches envelope and acknowledgement; no SDK inherited override replay |
| Concurrency | Critical | Mark consumed before await; closed scope excludes late dispatch/telemetry |
| Data layer | High | Phase counters only; accepted before journal/download; download failure retains accepted |
| Errors | Critical | Unknown, timeout, content policy, masked acknowledgement, foreign response never retry |
| Paths | High | Private token file validator and cleanup; no token/provider secret output |
| Transport | Critical | Official POST endpoint before solving; validate exact frame/project/count first |
| Headless | Medium | Offline coverage only; root E2E later |
| Boundaries | High | Retry strict integer 1..10; distinct known providers; invalid token falls through before Google |
| Observability | Critical | submitted immediately before dispatch; accepted only positive matching records; rejected only typed refusal |
| MCP | Low | REST-only existing controls; no new CLI/MCP surface |

Given a supplied token and retry 10, when Flow refuses, then one submission occurs.
Given an accepted image then download failure, no second solve occurs and accepted remains terminal.
Given an uncertain reply or foreign request, no fresh attempt occurs.
