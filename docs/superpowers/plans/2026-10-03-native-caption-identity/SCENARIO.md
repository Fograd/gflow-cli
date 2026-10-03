# Scenario: Owned image references with repeated captions

## Coverage map
D1/D2/D4/D5: no auth, solver, generation retry or profile lifecycle changes.
D3/D9/D11: exact token and outgoing ID remain the identity contract.
D6/D7/D12: fresh snapshot ownership/refusal and private-value handling remain.
D8: no paths introduced. D10: real headed picker proof remains distinct.
D13: shared SDK covers CLI/direct and queued MCP; unregistered native REST is R02.

| Scenario | Severity | Expected behavior | Evidence |
|---|---|---|---|
| Two active owned images share a caption | High | Hydrate exact requested UUIDs | SDK regression |
| Desired token is second picker result | High | Bind only desired token | Combined SDK/picker regression |
| Wrong token offered with identical caption | Critical | No Enter or submission | Negative regression |
| Foreign/archived/duplicate workflow or media | Critical | Refuse before mint | Existing ownership matrix |
| Wrong final ID / canonical ordered spans | Critical | Guard aborts | Existing wire/prompt regressions |
| Unsafe or absent caption | High | Existing refusal unchanged | Existing caption matrix |
| Real repeated-caption picker | High | No-submit attachment only | Tagged live BDD; acceptance separate |

## Must-cover before merge
Positive hydration-to-picker and wrong-token refusal, existing ownership and final-wire negatives.
No live accepted generation claim from attachment tests.
