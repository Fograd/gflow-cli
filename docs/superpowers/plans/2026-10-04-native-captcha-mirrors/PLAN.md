# Native CAPTCHA public mirrors plan

Goal: add existing provider controls to saved-voice create and native promotion CLI/direct MCP, with an explicit saved-voice SDK service bridge.
Architecture: one secret-free public validator; existing native policy and solver, fresh savedvoice service attempts, existing promotion worker policy. DefaultNone, one-use supplied tokens, no queued tokens or legacy control exposure. Parent approved narrow scope.

- [x] Predict and scenario risk analysis.
- [x] Add RED service/control/CLI/MCP tests (21 failed before implementation).
- [x] Implement validator/service and explicit adapters.
- [x] Validate accepted/unknown no-retry, fresh clients, omitted controls, token conflicts and registered schemas.
- [x] Update CLI/MCP/scope/environment docs; no new configuration.
- [x] Focused test/type/lint/docs verification and patch handoff.
- [ ] Parent full gate/publication and optional live acceptance.

Next native reference/edit/extension/image upscale remain separate follow-up. Image generation uses ImageOverrides rather than the native token scope, so it must not be routed into this policy without its own bounded adapter assessment.
