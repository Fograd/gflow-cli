# Bounded native account project traversal
Goal: R03 multi-page native project enumeration across SDK/CLI/direct MCP/REST/private worker, with honest continuation and counts.
Prediction: Architect/Security/Performance/UX GO8; root Devil CAUTION8: page exhaustion is not stable snapshot completeness.
Scenario: D1existingprofile; D2zero generation; D3strict single correlated page; D4no replay; D5one lease180s including checkout; D6no persistence/deletion; D7opaquecursor4096 unchanged; D8cycles/duplicateIDs/emptywithcursor/cap; D9rendernative names safely; D10releaseonerror/cancellation; D11distinctcounts; D12redunit/adapter tests/livepagedreads; D13allmirrors.
One-page default retained. all_pages actualbool; max_pages optional actualint1..100, only with traversal. Capped returns unconsumed next_cursor, pagination_exhausted=false, complete=None. Reject duplicateUUIDs/cycles ratherthan reconcile conflicting pages. Initial cursor identifies continuation scope.
- [x] Predict/scenario and standing authorization.
- [x] Red traversal and invalid controls/cleanup tests.
- [x] Shared one-lease traversal.
- [x] SDK/CLI/MCP/REST/privateworker forwarding, docs and website/skill mirror truth.
- [x] Read-only multi-page verification and required gates/council/publication/deployment.
Attached media/history and account-wide character/voice synchronization remain later R03 work; no feature narrowing.

Published/deployed5b877043; offline6068pass5skips89%coverage. ActualREST/MCPprojecttraversal readproof passed with registered37tools.
