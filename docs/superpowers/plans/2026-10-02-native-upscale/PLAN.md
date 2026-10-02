# Native Flow upscale integration

**Goal:** Restore native 2K image upscaling on the migrated composer and expose image/video exports to CLI and MCP.

**Architecture:** Integrate the reviewed upstream PR #922 delta onto v0.82.1. Flow's own browser creates the captcha and calls SPrCad; the shared client saves validated output. Preserve the legacy image path, profile leases, and account tier enforcement. User authorisation covers autonomous implementation and image tests; no video generation is authorised here.

**Predict verdict:** CAUTION. Architectural fit is established by the upstream implementation and tests. Security review requires bounded base64 decoding and removal of raw exception details. Performance adds one project navigation per export and bounded asynchronous waits; no background workers or additional Chrome instances. CLI/MCP mirror imports are owned here; REST integration is owned by the parent task. Reuse is materially simpler than a second private RPC transport.

| Risk | Mitigation |
|---|---|
| Oversized encoded media allocates unbounded memory | Cap image at 50 MiB base64, video at 350 MiB; browser blob conversion bounded |
| Raw exceptions expose sensitive response data | Log exception type only, generic parse errors |
| Selector drift looks like subscription limit | Disabled option returns UpscaleUnavailableError; missing option returns selector drift |
| Profile contention | Existing client ProfileLease, no browser process killing |
| Video spend | Offline tests only until a previously generated clip is supplied |

- [x] Import upstream tests; demonstrate missing driver failures.
- [x] Integrate PR922 production/adapters/docs without upstream version regressions.
- [x] Demonstrate red cap tests, then add bounded decode and strict base64 validation.
- [x] Run native live 2K output with dimensions, Pro 4K refusal, and MCP image path.
- [x] Run BDD-bound live regression and offline guards.
- [ ] Run full repository gates through the parent task before commit.

No new CLI image parameters are introduced. Video upscale leaf and both MCP twins come from PR922. CLI/MCP upscale calls are direct; they do not use worker payload codecs. The REST jobs layer serialises these calls separately.
