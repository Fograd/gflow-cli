# Image upscale capabilities implementation plan

Goal: expose fresh 2K/4K menu availability for an exact owned image before a paid request.
Architecture: shared menu opening/disabled state helpers, bounded read-only SDK orchestration, CLI/direct MCP/REST mirrors. No persistence or queued payloads. Predict CAUTION 7/10; ownership, unknown-state, and bounded observation mitigations implemented.

- [x] Write failing core and mirror tests plus browser BDD.
- [x] Implement shared menu observation and selected-engine timeout normalization.
- [x] Add bounded exact owned-image SDK read.
- [x] Add CLI/direct MCP/REST mirrors and strict response validation.
- [x] Document limits; focused tests, type/lint, and intercepted Patchright BDD verified.
- [ ] Optional original pro3 read: held while parent owns the profile.
- [ ] Parent integration, full gate, publication/deployment and generated website docs.

Changed files and exact verification are recorded in the private integration checkpoint. No commit, full gate, or production changes performed by this agent.
