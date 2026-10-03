# R06 scoped native supplied-token controls
Goal: unify supplied-token controls for applicable native generation surfaces without claiming provider acceptance or retrying uncertain writes.
Predict Architect/Security/Performance/UX GO8: ContextVar mutable single-use state, exact project/action/host binding, consume synchronously, reset finally, independent scopes and shared child consumption. RootDevil CAUTION8: no fallback on mismatch/reuse; no raw token in persistence/errors/argv; arbitrary worker secret paths prohibited.
Scenario: absent scope browser mint unchanged; correct matching native page/action one supplied token; wrong host/project/action and second consumer fail before browser work; child race one winner; independent tasks separate; cancel/exception reset.
- [x] Red shared-scope and secret/file tests.
- [x] Shared scoped native-token helper and TokenMinter integration.
- [x] Applicable SDK/CLI/direct MCP/REST/privateworker controls and documentation mirrors.
- [x] Controlled free interception BDD; completegates/council; publish/idledeploy.
Provider controls remain guarded until accepted Google proof. Native exports that do not mint CAPTCHA refuse controls. R07 promotion will use same scope; provider replacement-token acceptance remains unfinished R06/R12.
