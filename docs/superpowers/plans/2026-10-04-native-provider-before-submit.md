# Native provider fallback before Google submission

Scope: explicit captchaOrder or captchaRetry=1 for native reference video, edit, extension,
promotion and audio preview. Existing browser mint unchanged without controls. Supplied
token takes precedence. Numeric seed and after-Google retry remain unsupported.

Scenarios:
1. Exact selected native project/action solves once; concurrent child cannot solve twice.
2. Supplied private token skips provider mint; mismatch fails before solving.
3. First provider solve fails, next configured provider solves before Google dispatch.
4. Failed mint is never counted submitted and never retried by native generation.
5. Dispatch records submitted once; exact acknowledged output accepts once.
6. Typed WAF/content refusal rejects; cancellation/network uncertainty records unknown.
7. Accepted CAPTCHA remains accepted when later save/download fails.

Implementation: shared scoped async token helper, before-evaluate dispatch hooks, after
validated ack outcome hooks, private provider minter using fresh trusted site key and actual
page URL. Offline TDD first, bounded fake RPC tests and strict types; root sole live caller.
