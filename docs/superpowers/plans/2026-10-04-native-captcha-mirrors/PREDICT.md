# Predict: native CAPTCHA public mirrors

Verdict: CAUTION, confidence 7/10. Five personas reviewed in two independent batches within the four-agent concurrency cap.

Architect GO8: reuse existing exact-negative-ack policy; voice policy outside complete fresh-client service attempt, create only. Security CAUTION8: accepted preview/save, unknown/cancel/poll/download never regenerate; token/order/retry mutually exclusive before token-file read/client. Performance CAUTION8: fresh sequential clients, completed teardown, one MCP profile lock across operation; no nested promotion policy. CLI/MCP UX CAUTION6: optional None; omitted browser once versus explicit retry=1 provider selection must be described; StrictInt1..10, unique supported provider names, camel payload keys only. Devil CAUTION6: narrow savedvoice/create and promotion adapters; no unnecessary generalization.

Required mitigations are represented in scenario tests and plan: omit defaults, exact existing predicate only, no secret payload/queue additions, preserve service uncertainty and token compatibility, no generation acceptance claims.
