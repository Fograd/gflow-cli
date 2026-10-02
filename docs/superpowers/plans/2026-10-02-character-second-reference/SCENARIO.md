# Scenario: second character reference

Active dimensions: D1/D2/D3/D5/D7/D9/D10/D11/D12/D13; D4 covers no write retry,
D6 covers stable identity retention, D8 is unchanged managed-path validation.

| Scenario | Severity | Expected | Verification |
|---|---|---|---|
| Unowned second reference after valid first | Critical | Reject entire request before C4 | Unit, REST integration |
| Registered video/cross-profile second image | Critical | Reject before worker dispatch | REST integration |
| Secondary member of generated image batch | High | Resolve measured owned batch membership | Unit |
| Second copy fails after first copy succeeds | Critical | Preserve created ref/project, no retry | Unit |
| Copy replaces rather than appends | Critical | Never report success unless both refs visible | Unit, live BDD |
| Elevated WAF / interrupted session | High | Fail boundedly; no solver or generation | Native typed partial handling |
| Probe cleanup | Critical | Delete only created entity; originals remain active | Live BDD |
| CLI/MCP mirror | Medium | No new CLI/MCP entry point; REST/native worker only | Documentation |

Observed UI contract: portrait copy slot0, body copy slot1. Both references retained
in authoritative catalog; both original images active after owned-entity deletion.
No Google generation was submitted. The browser-only scenario is bound by
`tests/e2e/test_selfhost_character_second_reference_bdd.py`.
