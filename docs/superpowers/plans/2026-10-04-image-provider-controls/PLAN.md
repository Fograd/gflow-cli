# Source-backed image provider controls

Goal: enable explicit ordered providers and bounded image CAPTCHA attempts without replaying uncertain or accepted generation.

Architecture: image worker installs one fresh ImageOverrides scope per attempt. Existing native policy rules are mirrored for image response evidence; default browser generation and seed rewriting remain unchanged. Composer hooks report dispatch and exact-request, exact-project/count acceptance or typed WAF refusal. Provider mint requires freshly observed public reload metadata and matching trusted current script key.

Predict verdict: CAUTION, source-positive implementation; independent parent council requested before HTTP enable. No live acceptance claimed. Existing KNOWN_ISSUES unusual-activity envelope provides the positive refusal reason; page-owned client branch already bypasses SDK retries.

Risks: duplicate billing mitigated by retry only typed WAF plus positive rejection before acceptance; concurrent/late callbacks mitigated by consume-before-await and closed scopes; secrets remain private and telemetry phase-only; provider latency bounded per solve and attempt. No new CLI/MCP flags; existing REST controls are integrated by root. No selector changes.

## Tasks
- [ ] RED focused scope, metadata, fallback, dispatch, acknowledgement and retry tests.
- [ ] One-use override lifecycle and scoped current metadata.
- [ ] Image policy and worker integration; retries 1..10 only positive dispatched WAF negative acknowledgement. Supplied token forces one sequence.
- [ ] Narrow composer image route/response hooks; preserve default path.
- [ ] Focused compatibility, lint and strict type gates; parent independent review and HTTP wiring.
- [ ] Root final live E2E; replacement acceptance remains unproved until then.
