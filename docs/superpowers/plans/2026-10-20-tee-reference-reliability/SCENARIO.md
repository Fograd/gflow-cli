# Tee Pipeline reference reliability — 2026-10-20

The existing REST adapter re-uploaded cached native asset IDs as local files and could lose typed upload/image failure receipts. Tee Pipeline did not pin image generation to its uploaded reference account. Fix those boundaries without changing Google request/auth/selector paths.

## Scenarios and evidence

| Severity | Scenario | Required result |
| --- | --- | --- |
| P0 | Accepted generation times out or emits exit 40 | Preserve job and unknown outcome; no automatic second generation or fallback |
| P0 | An uploaded native ID is rebound to another account/project | Reject before native generation |
| P1 | Two same-account/project cached native UUID references | Preserve ordered IDs; do not turn them back into local uploads |
| P1 | Existing cached source comes from another project | Retain explicit local copy path and fresh validation |
| P1 | Account default project changes after admission | Preserve frozen job project |
| P1 | Old accepted idempotent request is read after upgrade | Return original receipt; changed request must still conflict |
| P1 | Upload fails/loses acknowledgement | Return typed assets receipt and generationSubmitted false |
| P1 | Tee's second upload returns another email | Stop before /images |
| P1 | Tee receives accepted-image failure | Keep safe receipt through caller wrapping |
| P2 | Existing CLI/MCP native references | Existing fresh native guard still executes; no CLI or MCP contract changes |

Repository regression tests establish red-to-green reproduction. The first live acceptance case uses a separate loopback server and private queue against an existing native profile for a public REST product photo. The second case uses the deployed Tee gallery and production Gflow connection for a persona photo after both fixes are deployed. Each case admits at most one new image. Each case reserves a persistent allowance before uploading, saves receipts and never automatically retries. Real embroidery blueprint and style inputs are reused. No videos, storefront publish, orders or UseAPI requests are in these cases.

Auth expiry, WAF refusal and native transport drift remain typed native outcomes; this patch does not guess around those conditions. SQLite/profile leases, private credentials, MIME/account/project validation and trusted-handle allowlists remain active. New offline cases include cross-platform/local-path boundaries and malformed public metadata. No native transport, selector or token-mint change is proposed.
