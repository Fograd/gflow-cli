# Scenario: useapi parity expansion

Active dimensions: auth/identity recheck; CAPTCHA secret boundaries; locale-invariant selectors; restart/resume; profile concurrency; SQLite checkpoints; redacted failures; contained paths; RPC schema/correlation; headed display; parameter limits; observable provenance; CLI/MCP parity when changed. Documentation-only changes do not exercise Flow.

| Scenario | Severity | Expected behaviour | Verification |
|---|---|---|---|
| Cross-account video ingredients | Critical | Refuse before submit | Offline API test |
| Crash between paid outputs | Critical | Preserve completed outputs, never replay unknown submission | Durable worker test |
| Client disconnect during synchronous wait | High | Job continues; idempotency retrieves it | API integration |
| Account cookies present but Flow identity check pending | High | Pending login, no false healthy status | Read-only browser probe |
| Asset used by queued job is deleted | Critical | Refuse deletion | Store integration |
| Seed or CAPTCHA supplied but not enforced | Critical | Refuse before submit | Observed wire/abort test |
| Solver key/token in error or persisted job | Critical | Never expose or persist public secrets | Failure/redaction tests |
| Native CRUD uses cached local data | High | Label provenance; do not claim Google mutation | Contract review |
| Null entity submit reply while Google accepted | Critical | Observe project-scoped new workflow, no automatic re-submit | Live video external blocker unless credit test authorised |
| New CLI option drops from queued MCP | High | Mirror signature and payload consumption | Parity tests |
