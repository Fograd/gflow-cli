# Scenario: measured cookie banner action fallback
Active D3/D5/D7/D11: source-backed structural selector variant, bounded ordinary click/wait, best-effort attribution, locale independence. Auth tokens, mutation wire, directCLI/MCP fields and profile state not changed.
| Scenario | Severity | Expected |
|---|---|---|
| Visible accept-only bar with learn-more link | High | Exact accept button normal click, hidden wait |
| Reject and accept present | High | Reject preferred, accept never clicked |
| Present reject click times out | High | No fallback acceptance, existing warning/post-mortem |
| No visible bar | Medium | No action lookup/click/wait |
| Actual pro2 controls occluded by bar | High | Root reruns measured no-generation capture; offline mocks do not claim live clearance |
Parent scoped tests to DOM-contract mocking and root sole live caller; fresh live acceptance remains root-owned.
