# Count-one generic video CAPTCHA providers

Approved root plan; first published batch freeze released at commit b8aba7b4. Root owns HTTP/docs/live verification. Agent owns generic transport policy, SDK service, CLI/MCP/queued mirrors and offline tests.

Primary proof: root abort-only generic count-one T2V capture observed a fresh Enterprise reload, VIDEO_GENERATION action, sitekey equal current trusted discovered key, one known UI request and zero forwarded submissions. No key, prompt, token or project belongs in this plan.

Architecture: configured providers use current captured metadata on the exact fresh selected project page. Only token field is rewritten. Each explicit WAF-only retry creates a new closed-state override, fresh provider keys/token and fresh requested UUID. No retry after positive, mixed/masked, unrelated, unknown, content/auth/timeout/cancellation outcome.

Critical scenarios: supplied token precedence/no retry; provider fallback before Google only; count>1 prebrowser refusal; missing/stale/foreign metadata before solve; duplicated request UUID before solve; exact Request + single raw exact-RPC negative WAF only; positive acknowledgment followed by poll/download failure; callback empty Context and close races; queued secrets refuse before enqueue.

Tasks:
- [ ] RED policy/metadata/identity and interface tests.
- [ ] Bounded shared policy and generic bridge metadata/outcome integration.
- [ ] SDK service, CLI/direct+queued MCP nonsecret controls; confidential queued token refusal.
- [ ] Private REST worker/runtime forwarding.
- [ ] Focused checks and independent review; root live verification/documentation.
