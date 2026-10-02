# Native character CLI and MCP consistency

Goal: expose the measured native character lifecycle through shared SDK, CLI and MCP without depending on the private REST registry.

Predict CAUTION8/10. Architect: reuse client pool and transport, shared portable service. Security: validate both source images/local integrity and authoritative active ownership before C4; no raw URLs or mutation replay. Performance: one checkout/finally return and one45s post-create deadline. UX: explicit create-from-images preserves old portrait generation; direct bounded MCP calls with explicit delete confirmation. Devil advocate: extend existing list/show/rm rather than parallel command trees; no new queue replay semantics.

The user authorised implementation and publishing; no further design confirmation is required. Alternatives considered: REST-only wrappers retain CLI gaps; a transport rewrite adds unmeasured behavior; shared SDK/native helper reuse chosen.

- [x] Red SDK/service validation, native dispatch and partial-outcome tests.
- [x] Shared SDK native create/update/list/delete and portable catalog-backed reference service.
- [x] CLI create-from-images/update and MCP create/update/rm mirrors with explicit deletion confirmation.
- [x] Actual native CLI/MCP lifecycle BDD, owned fixture cleanup, source preservation.
- [x] Six-axis docs/mirrors, full gates and independent review.
- [ ] Fork publication.

No portrait/TTS/video generation is needed for this lifecycle. Old portrait-generating create remains a separate path; no complete parity claim.

Actual first CLI/MCP BDD reproduced a notes-clear acknowledgement bug after successful two-reference/Charon creation (2 failed in140.73s). Both test entities were cleaned; native-owner fix and surface rerun are required before marking live proof complete. Invalid SDK project IDs now fail before page checkout (red-to-green regression).

Final proof: three CLI/MCP character/inventory scenarios passed in265.40s; strengthened SDK inventory passed in11.42s; deployed HTTP preset/change/notes-clear lifecycle passed in123.99s. Final offline5220passed47skipped90.71% in218.95s. Publishing this verified scope is a checkpoint within the continuing full-useapi task.
