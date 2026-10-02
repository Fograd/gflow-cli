# Native second character image reference

Goal: accept a second registered, decoded PNG/JPEG on the same account/project and preserve the first character image plus both originals.

Predict CAUTION (8/10): architecture reuses native character copy helper; security requires atomic validation of both registered image references before C4; performance requires one shared post-create45s deadline; UX must distinguish append from replace and preserve partial created identity; devil's advocate requires actual UI wire evidence before extending Sc7 arguments. This is a private worker/REST feature; no new CLI/MCP command is proposed, so no CLI/MCP mirror is claimed.

Must-cover scenarios:
- D1/D5: exclusive normal profile lease; no browser kill or simultaneous probes.
- D2/D10: headed existing session; guard all generation RPCs; no solver/task submission.
- D3: inspect structural portrait/body tabs and upload/picker component transitions, do not infer absence from selector misses.
- D4/D7/D12: second copy fails after first succeeds; return partial character reference/project, no creation retries or deletion of uncertain state.
- D6/D9: acknowledge both copied workflows in authoritative entity; preserve first reference, both original active media, and drop signed URLs.
- D8/D11: same-profile/project managed PNG/JPEG only; UUID source identities, reject missing/cross-profile/video/unsupported third ref before any mutation.
- D13: no CLI/MCP option added; private native worker codec and public REST route both require matching tests.

Tasks:
1. Observe owned first-reference character and second-reference UI action using two existing test images. Capture actual RPC argument index and before/after metadata. Record append/replace/error reading before probe.
2. If append proven, scaffold unit validation/partial outcome tests and opt-in BDD proving two copied refs and preserved originals.
3. Extract common measured copy operation; extend worker payload optional second_media_id and validate both before creation. Parent owns REST registry validation and adapters.
4. Keep all copies/visibility/personality inside shared post-create45s timeout, preserve created ID on any partial outcome.
5. Run focused offline gates, live HTTP BDD and owned probe cleanup; update public evidence/docs and whole-tree gates via root.

Pre-registered outcome readings: two distinct refs remain = append proven; first disappears = replacement (do not enable imageReference_2 under append claim); selector miss = inconclusive; generation RPC encountered = abort and investigate; source archived/deleted = STOP and restore only owned affected test media if reversible.


## Execution status

- [x] Actual UI body-slot copy observed with index1; portrait index0 retained.
- [x] Authoritative two-reference retention and both source preservation observed.
- [x] Red ownership test and browser-bound BDD scaffold created before adapter edit.
- [x] Shared native copy helper and atomic batch-member ownership implemented.
- [x] Native worker forwards both media IDs and one caller-verified image assertion.
- [x] Partial outcome and replacement-refusal tests pass; no mutation retry added.
- [x] Live adapter BDD passed1 in34.11s; all owned probes cleaned up.
- [x] Focused native tests, Ruff and strict typing pass.
- [ ] Root actual HTTP BDD and whole-tree publication gates.

No CLI/MCP command was added; this extension is private native-worker and REST.
