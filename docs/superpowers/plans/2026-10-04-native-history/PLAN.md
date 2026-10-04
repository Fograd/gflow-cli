# Measured native account history

Predict: GO for bounded read-only LWkPYd continuation after source declaration and
private two-page proof. Default [] returned 20 workflows / 20 media; [20, exact
returned cursor] returned 20 disjoint workflows / 20 media and changed cursor.
No generation or mutation; root owns captures under pro1-history-observation.

Contract: request size field1 fixed20 / opaque cursor field2. Response workflows
field1, cursor field2, media field3. Fresh workflow[0]/project[4] and media
[0]/project[1]/workflow[2] joins must match; observed primary media at workflow
metadata[4] must match its returned owned media. Stable IDs/type/dimensions only;
never return captions, prompts, signed URLs, or derive deletion from absence.

Scenarios: strict control validation before lease; duplicate/cross-owner rows;
primary-media mismatch; malformed collections/cursor; cursor cycles and duplicate
IDs across pages; atomic page media caps with last accepted continuation retained;
45-second timeout yields only prior completed verified pages; zero completed pages
timeout refuses. One lease and one request per page; default one page, explicit
max50 pages/max1000 media. pagination_exhausted is separate from complete=None.

Tasks: tests first; pure parser and bounded SDK orchestration; focused offline
validation. Root owns shared RPC allowlist / SDK client / surface wiring and real
free affected-surface acceptance. No paid or browser calls by this agent.

Offline validation: 24 parser/control/traversal regressions pass. Ruff and targeted
Pyright pass; no browser or Google calls. Explicit initial [20,null] uses the
requested fixed-size schema and passed the actual SDK BDD:1test in18.39seconds,
40workflows/media across2pages, exactjoins and guarded zero writes. Earlier measured
evidence includes [] default and [20,opaqueToken] continuation.

Coordinator actual SDK BDD:1test passed18.39seconds, explicit [20,null] and next
cursor yielded2pages/40joined workflows/media, zero guarded writes. Pro2/pro3
bounded45-second reads observed300/220 workflows/media over15/11 pages,
timed_out:true, complete:null, pagination_exhausted:false, resumable cursors;
each observed one project/no audio, without asserting complete history.

REST-only inventoryObservations metadata upserts now have17unit and30combined
module/server-hook passes. Exact configured account/profile scope, no URL/prompt/
caption/cursor persistence, no absent-row deletion and no GetMedia authority.
Actual REST BDD and final full frozen-source gates remain pending.

Actual REST history/synchronization BDD passed1test in18.77seconds:2pages,40media
and workflows, durable observed counts, exact joins and unknown completeness.
Observation/HTTP regressions passed30tests. Council ownership/privacy review
returned GO: exactaccount/profile scopes, atomic conflicts, metadata allowlists,
noURL/cursor/caption persistence and no cached ownership authority.

Frozen-source history gate:6556tests passed,5skipped,89%coverage in211.92seconds.
Hygiene, documentation links, public PII, generated mirrors, council references,
Ruff, formatting and strict source Pyright passed. Publication/deployment is
recorded separately; source functionality does not prove paid R04 acceptance.
