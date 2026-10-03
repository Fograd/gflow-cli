# Cookie-table import implementation plan

Goal: accept bounded useapi-style DevTools cookie tables, install a private staged
Chrome profile, and verify real Flow access before account registration.

Scope comes from the standing full Google Flow parity request. Account creation
is free; no generation is needed. The normal headed Chrome launch and profile
lease remain authoritative. Workstation instructions use Vivaldi; transfer of a
device-bound session can fail and must never become an authenticated claim.

Predict: Security and Performance CAUTION/8: exact Google domain allowlist,
secret-free errors/repr, finite size/rows/values, no active-profile swap, candidate
cleanup and actual expected account identity verification are required. Architect,
UX and Devil CAUTION/8: explicit supported column mapping, documented expiry and flags, no secret-rich preview or active-profile replacement. Mitigations are required in tests before integration.

Scenarios: malformed/truncated TSV; headers and headerless browser table; session
versus ISO/epoch expiry; duplicate identities; unknown/partitioned semantics;
non-Google domain and cookie-prefix violations; oversize and expired cookies;
error output never contains values; busy original profile; failed candidate
preserves original; authenticated candidate still needs real project access;
expected account mismatch; cancellation closes browser and releases lease.

- [x] Red pure-parser tests and offline BDD for safe errors and ambiguous input.
- [x] Parser with bounded validated Playwright cookies; no authentication claims.
- [x] Isolated import and identity/access verification with cleanup and lease tests.
- [x] HTTP cookie import integration after HTTP job agent releases server ownership.
- [x] CLI/MCP import adapters or explicitly justified interactive-only scope, six mirror axes.
- [ ] Free native browser BDD using a private isolated copied session; no source profile mutation.
- [x] Documentation, quality gates and independent review.
- [x] Publish and deploy; root continues remaining parity work.

No secrets, cookie examples with real values, private identifiers, HAR or session
captures may be committed. No secret-rich useapi response is mirrored: responses
contain safe metadata only. Existing operator-attested registration stays explicit.

Evidence: strict parser, CLI import, HTTP activation/refresh and offline BDD
checks pass. Cancellation/close fault tests cover actual candidate-population
lifecycle with fake contexts. Independent review findings (FIFO blocking,
post-rename fingerprint failure, candidate ACL cleanup) were corrected with
fault regressions. A private native clone attempt was rejected before activation;
the original profile required a Google identity check afterwards, but causality
was not established. User completed that challenge; real original-project access
was verified. Successful live cookie import remains an explicit proof gap.

Frozen-source full regression: 5495 passed, 28 skipped, 15 warnings, 90.62% coverage in 238.49s. Whole-tree Ruff/strict Pyright and documentation/privacy/mirror gates passed.

Published/deployed fd56b2e6. Production queued health and registered MCP protocol passed; no generation in that deployment smoke. Successful cookie transfer remains unproven.
