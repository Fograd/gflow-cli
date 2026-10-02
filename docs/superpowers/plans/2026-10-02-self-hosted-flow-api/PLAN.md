# Self-hosted Google Flow Implementation Plan

**Goal:** Replace the paid Google Flow intermediary with an authenticated service owned by the user, including native image upscaling and useapi-compatible calls.

**Architecture:** Keep the upstream CLI and browser/profile leases. Add an isolated `selfhost` HTTP adapter using SQLite jobs and one serial execution lane per configured account. Reuse upstream PR 922 for migrated image/video exports after review and local tests.

**Authorisation:** User explicitly requested the fork, all Google Flow features, autonomous implementation and image tests. Keep the existing production tee provider unchanged until the new endpoint is verified.

**Constraints:** No secrets or account identifiers in source. No tier bypass; 4K depends on Google entitlement. No uncertain job replay after process restart. Unsupported request controls fail explicitly, never silently disappear. Video generation verification remains gated by the user's credit authorisation.

## Tasks

- [x] Create user-owned GitHub fork and isolated source checkout/branch.
- [x] Inventory every documented Google Flow endpoint and parameter in `docs/self-hosted/PARITY.md` against the actual CLI/service contract.
- [x] Review PR 922; integrate native migrated image upscaling, video exports and MCP adapters with regression tests.
- [x] Add `src/gflow_cli/selfhost/` HTTP service, durable job store, authentication, request validation, profile scheduling, upload ownership and protected result retrieval.
- [ ] Expose existing image/video/entity operations through useapi-compatible routes. Reject unsupported features explicitly with documented reasons.
- [x] Verify request authentication, malformed input, upload limits, profile ownership, idempotency, interrupted jobs and callback allowlists through `tests/selfhost/`.
- [x] Run native 2K image upscale against a saved image and inspect actual output dimensions. Run image generation through HTTP and the existing tee client contract.
- [x] Deploy a separate systemd user service on CC LXC with environment/secrets files and verify unauthenticated requests fail.
- [ ] Record exact feature/test status; run repository checks and review; publish changes to the user's fork.

## Risk review

Architect and UX: separate single-user adapter is justified by user scope despite upstream SaaS non-goal. Tee expects HTTP 200 job acceptance, inline base64 image results and nested uploaded identifiers.
Security: preserve upstream profile leases, bound file sizes, validate paths and identifiers, constant-time bearer comparison, avoid arbitrary URL fetches, and restrict callback hosts.
Performance: serial browser actions per account prevent corrupt profiles; three configured accounts may run independently only when authenticated.
Recovery: a claimed job is uncertain after a crash, so mark it interrupted rather than submitting it again.
Scope: API route presence does not prove provider parity. Record observed unsupported controls and native operations still requiring migrated ports.
