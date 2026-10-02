# Self-hosted fork verification

Measured on 2026-10-02 using one authenticated Google AI Pro profile served by `flow.google.com`.

| Surface | Evidence | Result |
|---|---|---|
| CLI native image 2K | Existing 1376×768 JPEG → 2752×1536, 3,334,707 bytes | Passed |
| Shared-client/MCP native image 2K | Three real-profile BDD cases, including Pro 4K refusal |3 passed |
| HTTP native image 2K | Durable job completed, inline JPEG 2752×1536, 3,334,707 bytes | Passed |
| Tee client text-to-image | Existing tee client used the local endpoint and received 458,359 bytes, 1024×1024 | Passed |
| Raw upload and reference generation | Existing tee request format produced blue mug variation from red source, 271,282 bytes | Passed |
| HTTP complete image workflow | Real HTTP BDD: generate → upload → reference generation → native 2K; asserts exactly doubled dimensions |1 passed in 133.91 s |
| Actual Streamable HTTP MCP upscale | Live tool call through the running service returned native 2K bytes after direct detail navigation fixed gallery virtualisation | Passed |
| Authentication | HTTP 401 without bearer on REST and MCP; authenticated MCP lists 18 tools including both upscale tools | Passed |
| Native HTTP seeded image batch | Two requested consecutive seeds 12042/12043 returned by Google, two decoded images at least 1024 pixels |1 BDD passed in 29.44 s |
| Native MP4 resources | Synthetic one-second MP4 upload with explicit per-upload rights confirmation, native selected-project list and reversible batch archive; no generation credits | Native worker BDD 1 passed in 32.07 s; HTTP REST BDD not performed |
| Initial offline regression | 4,911 passed, 30 skipped; 91.26% coverage; one README sponsor-placement failure | Placement corrected and targeted test rerun |
| Expansion offline regression | 4,960 passed, 49 skipped; 88.18% coverage; three environment/marker failures | Added missing resource BDD tags, restored uv PATH; 142 focused tests passed; final targeted gates recorded below |

The one real-profile native-upscale BDD run had a profile contention/setup failure while another test was using the account. It was repeated without concurrent browser work and all three cases passed. Profile leases rejected contention safely; no browser was killed.

## Explicit limits

Only one of the user's three Pro accounts is authenticated and configured for execution. Successful 4K cannot be tested without an Ultra account; Pro 4K refusal is verified. The three plans are independent allowances, not an Ultra entitlement.

No video generation credits were spent during this implementation. Native video 1080 p/original 720 p/GIF export adapters have offline coverage, but no existing Google-generated video was available for live validation. Other unsupported controls and endpoints are listed in [the compatibility inventory](PARITY.md). API presence is not proof of full useapi parity.

Tee's production provider was not switched. Its existing client was exercised against the new endpoint by overriding its base URL in an isolated verification process. The local service and fork can be used independently of that production configuration.

CAPTCHA provider configuration and token hooks have offline coverage. Actual Google acceptance remains unverified despite the later paid CapSolver trial below. Earlier JavaScript metadata hooks failed; the later native reload parser supersedes them. Neither metadata nor key storage is successful live solver acceptance.

The expanded service was restarted with no active jobs. Authenticated capability discovery and provider configuration returned HTTP 200; unauthenticated capability discovery returned HTTP 401. Video generation remains disabled.

The main-world and early-hook CAPTCHA probes were aborted before Google submission and still returned no action metadata. Those historical probes were superseded by native reload capture below. Provider generation continues to return HTTP 501 pending actual third-party acceptance; key configuration remains usable. Final focused API/transport/MCP verification:157 passed.

Final complete offline regression (with corrected marker/PATH setup): **4,969 passed, 47 skipped; 90.36% coverage** in 208.80 seconds. Whole-tree Ruff format/lint and strict Pyright passed; documentation links, repository hygiene, website privacy/mirror and council-memory checks passed. Duplication proxy found only pre-existing experimental/CLI-MCP mirrors.

A bounded ten-image reliability pilot returned nine images across four submissions, with no explicit CAPTCHA refusal observed. One four-image batch returned three; a diagnostic repeat returned four. The test found and corrected REST partial-count completion handling. See [the full evidence and limits](STRESS_TEST.md).

Post-stress reporting-fix regression:4972 passed, 47 skipped; 90.39% coverage. 94 selfhost tests passed, including short/exact/excess result counts and preserved assets. Whole-tree lint/format and strict types passed.

Native CAPTCHA reload parser passed three abort-only metadata probes (IMAGE_GENERATION action and trusted-query-matched site key), superseding the earlier failed JavaScript hook. Fresh same-page TokenMinter replacement BDD submitted but Google rejected unusual activity (WAF 403/gRPC 7); no image was accepted. This is not successful CapSolver or external-token acceptance; provider generation remains disabled with HTTP 501.

Actual paid CapSolver trial: solveStarted 1 / solved 1 / submitted 1 / accepted 0; one replacement submit rejected PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7/HTTP 403), no retry. Provider generation remains disabled with HTTP 501. CLI/SDK/MCP/queued seed support now has offline parity and a callback-context regression fix; the corrected CLI path later produced one accepted native image with actual seed 42, JPEG 1024×1024 and 397,336 bytes, without a solver or retry. The successful REST seeded batch above is a separate proof and does not establish CLI/MCP live seed verification.

Corrected CLI seed proof: one native submission returned seed 42 and a 1024×1024 JPEG (397,336 bytes), no solver and no retry. MCP/queued seed paths have offline parity; this CLI result does not claim separate live MCP verification.

Native account project paging was measured through UpteDb: two pages of 21 entries with disjoint project IDs and opaque continuation. The adapter exposes explicit source=google; useapi history aggregation remains unported.

Deployed native HTTP catalog BDD: **1 passed in 33.03 seconds**, with no generation or solving. It verified two disjoint native account project pages, project-scoped character summaries and dynamic system voices. Earlier observations measured 42 distinct projects across two pages and 30 system voices. Native character bound-reference create/update/delete still needs its own proof. Latest full repository regression is being corrected and rerun; prior successful gates above apply to their recorded revisions, not an all-green claim for current edits.

Native character adapter proof passed without generation: create draft, copy an existing owned image into it, observe visible project catalog, update name/personality and delete. The source stayed active and copied workflow differed; probe characters were cleaned up. The deployed HTTP CRUD BDD later passed as recorded below. Initial personality-on-create is implemented through a validated post-copy update; second reference and voice remain unsupported. Initial-personality HTTP CRUD is live verified.

Deployed HTTP character CRUD BDD: **1 passed in 91.94 seconds**, without generation or solving. It created a character by copying an existing owned image with initial notes, PATCHed notes, GET-verified stored references/notes, DELETEd it, confirmed HTTP 404 and verified the source image remained active. All test entities were cleaned up. This proves the limited one-image metadata flow; second reference and voice assignment remain unsupported.

Latest stable publication gate: **5,085 passed, 47 skipped; 90.44% coverage**, in 223.54 seconds. Ruff checked 570 files cleanly and strict Pyright reported zero errors. Tracked repository hygiene, documentation links, privacy/mirror and council checks passed; staged private-identifier and actual CapSolver-key scans were clean. This gate covers the published implemented scope, not complete useapi parity. Second-reference investigation remains a spike outside this snapshot.

Two-reference native adapter BDD: **1 passed in 34.11 seconds**. Deployed two-reference HTTP lifecycle BDD: **1 passed in 97.82 seconds**. Both references were validated atomically before creation, copied into measured portrait slot 0/body slot 1, persisted, and both source images remained active; the owned test entity was removed. The shared post-create deadline remains 45 seconds. The final second-reference gate passed as recorded below.

Second-reference stable offline gate: **5,098 passed, 47 skipped, 15 warnings; 90.56% coverage**, in 219.93 seconds. Strict Pyright reported zero errors and Ruff checked 571 files cleanly. Duplication checks found only the same three pre-existing unchanged findings. The manual six-axis CLI surface check is not applicable to this change: it extends REST/worker adapters without changing CLI commands. Post-staging hygiene/privacy checks are recorded by the publication step.
