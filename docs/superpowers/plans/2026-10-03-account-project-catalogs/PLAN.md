# Account project catalog aggregation
Goal: finish R03 cross-project visible media/workflow/character/saved-voice enumeration within bounded project listing, with no absence-based deletion.
Prediction Architect/Security/Performance/UX GO8; root Devil CAUTION8: returned subset and opaque nextprojectpage cursor are different from unread listed projectIDs.
Constraints: include_catalogs actualbool, max_projects actualint1..20(default20) onlywith inclusion, Google-only controls. One leased page and one fresh payload per project feeds allfour typed projections. 180sec whole deadline including checkout/traversal/metadata. Refuse duplicate workflow/entity/voice/media IDs, unrelated ownership and unsupported shape. No rawrows/signedURLs/playbackURLs/Storewrites/deletion inference.
Scenario D1auth unchanged; D2readonly0gen; D3measuredparsers; D4no writes/replay; D5onepage; D6typedmetadata/no cache; D7opaquecontrols bounded; D8duplicates,empty,unrelated,unknown,caps; D9native captions/names preserved; D10failure/cancelreleases; D11counts/pendingIDs/cursor distinct; D12red+BDD; D13SDKCLI/directMCP/REST/worker/docs.
- [x] Predict/scenario and standing authorization.
- [x] Red typedprojection/URLexclusion/ownership/caps/one-read/controls tests.
- [x] Shared pure projection and one-page enrichment.
- [x] Public adapter forwarding and documentation mirrors.
- [x] Read-only one-project BDD; requiredchecks and council.
- [x] Publication and idle deployment at05c3b632; both services active.
Pagination/history completeness still unknown; this enumerates discovered native catalogs and does not claim atomic account history.

Live one-project catalog BDD1pass2warnings10.14s with concurrency1/0generation. Registered MCP strictbool/int controls red6coercion failures, then green. Mirror sweep SDK/CLI/directMCP/privateworker/REST, no queued mutation; docs/skill/plugin/website updated, existing error codes preserved.
