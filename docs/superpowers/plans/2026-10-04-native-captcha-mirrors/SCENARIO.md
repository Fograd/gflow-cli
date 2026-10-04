# Scenario: saved voice and promotion provider mirrors

Active dimensions D1/D2 token scope and WAF; D5 fresh sequential clients/ProfileLease; D7 typed input and uncertainty; D9 accepted preview/save/poll/download; D11 bool/integer/provider bounds; D12 secret-free observations; D13 explicit CLI/direct MCP/SDK parity. No schema/selector/browser/auth implementation changes, batch resume or new path handling.

| Scenario | Severity | Expected | Test |
|---|---|---|---|
| Omitted controls | Critical | Browser-owned one attempt; no provider payload defaults | Unit/adapters |
| Explicit retry1 | High | Existing configured provider selection | Unit/adapters |
| Exact negative WAF acknowledgment | Critical | Existing policy retries within1..10, fresh client/token each | Service |
| Accepted preview followed by save failure or late WAF | Critical | Never replay speech | Service |
| Unknown/cancel/poll/download/teardown | Critical | Preserve handles/error and never retry | Policy/service |
| Token plus order/retry | Critical | Typed refusal before file read/client | SDK/CLI/MCP |
| Invalid provider order/bool/0/11 | High | Typed refusal, no operation | Unit/schema |
| List/get/delete controls | High | Refuse provider controls on noncreate | Service |
| Direct versus queue | High | Direct tools only, no codec/token queue change | Adapter/schema |

Known issues: per-profile WAF refusals, manual renewal and native TTS Google refusal remain open; exposing policy does not establish Google acceptance. Existing native CAPTCHA/promotion browser BDD covers transport; no transport/selector behavior changes in this batch. Live paid acceptance is parent-owned and prohibited for this agent.
