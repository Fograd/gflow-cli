# Predict: generic image provider mirrors

Verdict CAUTION7 mitigated before implementation. Architect/security/performance
review GO8: existing ImageOverrides engine supports exact daemon generation
callback; same client matches REST policy, fresh scopes per attempt, no native
token engine. UX/devil CAUTION7: optional None versus explicit retry=1 selection,
single-prompt CLI scope, strict project/count/order/attempt validation, confidential
queue refusal and actual codec/daemon round trip must be tested.

Mitigations: omitted controls bypass policy; observed native HTTPS host and UI
transport before selected generation; count/seed match SDK request; exact existing
override correlated negative acknowledgment is the only retry predicate.
Downloads, attribution, recording/completion and cleanup outside policy.
Accepted/partial/unknown/cancelled never replay. Queue checkpoints unchanged.
Provider setup failures become privacy-safe actionable typed errors.
