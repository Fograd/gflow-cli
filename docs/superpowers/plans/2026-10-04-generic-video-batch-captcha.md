# Generic batch CAPTCHA controls

Approved by root after independent core GO. Scope: current single generic submit RPC with 1–4 rows and one common 11-slot CAPTCHA context; no per-output token invention.

1. RED tests: count2–4 supplied/private/provider policy acceptance, all-four-RPC canonical seed vector guard, stale/reused member refusal before solving, pure WAF retry with zero actual handles, partial/mixed/accepted no replay, all mirror forwarding.
2. Reuse VideoOverrides token rewrite for common context. Validate every canonical requested UUID before mint, unique within the vector and entirely absent from earlier attempts; update previous IDs atomically.
3. Batch observer validates exact request project/mode/count/bound references first, applies one override, correlates one same-RPC raw response, then marks accepted only after all output IDs are proven. Refusal marks rejected only for one typed negative reply with no actual handles. Cleanup/partial/poll/download becomes unknown or accepted-late-failure and cannot retry.
4. Reuse trusted fresh Enterprise VIDEO_GENERATION metadata and current discover_site_key checks. Supplied token wins, consumes once, never retries; provider fallback occurs only before Google, explicit WAF-only max10 retries use entirely fresh vectors.
5. SDK public wrapper/CLI/direct+queuedMCP/private REST worker select additive batch for N>1; confidential queued tokens remain refused/private-file managed.
6. Root owns HTTP control validation, docs, live count4 abort proof and spending. Owner has no live/browser/solver calls. Actual plural accepted rendering remains R12 pending allowance.

Evidence: current t7a sends every row plus one shared context; current gy.dg exposes repeated field4 Lx media; generic root abort proof already measured the current 11-slot Enterprise context/action/sitekey. Batch core source-proven request assignment and repeated acknowledgment is independently reviewed.

Review constraints inherited from root/R08: exact official POST origin/path and Request correlation; every canonical ID fresh; no false handles; one-use context; no accepted/partial/masked/unknown/quota/content/auth replay; no protected URL or secret in durable queue; default browser behavior and singular DTO unchanged.
