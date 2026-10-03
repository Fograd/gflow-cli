# Native caption identity
**Goal:** Allow distinct owned image UUIDs with the same caption to reach exact-token selection.
**Architecture:** Remove only global caption uniqueness in fresh native image hydration.
No identity, workflow, model-budget, picker safety or outgoing-wire guards change.

## Predict: GO with conditions
Architect GO: labels are not identities; existing shared SDK boundary is appropriate.
Security GO8: retain owned active typed media/workflow and outgoing ID guards.
Performance GO8: no added page reads, writes or retries.
CLI/MCP UX GO8: shared hydration; no parameter or codec changes; REST native R02 remains.
Devil's Advocate CAUTION: combined SDK-to-picker positive and wrong-token negatives required.
Conditions resolved by the regression matrix below. Live acceptance stays separate.

## Tasks
- [x] Add failing hydration/SDK-to-picker regressions and tagged no-submit live scenario.
- [x] Remove only the caption collision guard; preserve all other validation.
- [x] Run focused matrices, live BDD and required repository gates.
- [ ] Document exact scope, pinned review, publish and deploy.

## Risks and mitigations
Repeated labels could conceal wrong assets: fresh UUID ownership + unique token + outgoing ID.
Unsafe captions remain refused: do not sanitize or truncate them.
Offline proof cannot establish accepted generation: record live no-submit/acceptance separately.
