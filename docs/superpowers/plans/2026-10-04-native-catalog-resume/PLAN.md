# Bounded catalog resume and durable observations

Status: implementation delivered, architecture GO; actual free BDD and final
frozen-source gates remain pending. No live acceptance is yet claimed. Continue within the authorized parity
roadmap, preserving existing project-list defaults and ownership boundaries.

Add optional SDK catalog_project_ids as an explicit ordered resume of1–20unique
project UUIDs. It requires include_catalogs=True and is incompatible with account
cursor, all_pages and max_pages controls. max_projects bounds enrichment; return
ordered remaining IDs without skipping. Read the same existing owned project
payload for each ID, with current deadlines and no write/reconciliation request.
Mirror CLI/direct MCP/privateworker/REST controls and validate before browser lease.

Extend REST durable observations with merge_catalogs: allowlist metadata under
the exact profile/configured account, including observed project, character entity
and saved-user audio/workflow identities. Record empty projects. Never store
URLs, prompts, captions, cursors or bundled system presets. Attached-media origin
must remain distinct from selected-project ownership; inventory membership does
not authorize mutation/reference/GetMedia.

Validate complete batch before committing and roll back transaction conflicts.
Retain previously observed missing rows; complete remainsNone. Counts describe
observations, not authoritative reconciliation or current full account inventory.

Delivery sequence: red parser/store/control tests; smallest shared implementation;
SDK/CLI/direct MCP/worker/REST symmetry; focused checks and final frozen-source
gates; actual free affected-surface BDD with bounded resume/metadata cache proof.
Root owns Google/browser fixtures; no paid generation is needed for this batch.
Update API/PARITY/VERIFICATION/agent/skill/site mirrors with verified scope.
R03 remains open for complete history/cohorts/authoritative reconciliation.

Implementation now wires SDK/CLI/direct MCP/privateworker/REST ordered resume
and REST scoped metadata resource observations. Actual free BDD/full gates pending.
Prior R02 a7f29324 is published/deployed; this new batch remains uncommitted.

Actual SDK catalog-resume BDD on pro1 passed1test,2warnings in14.52seconds,
with zero generations. Actual REST resume/durable-observation BDD passed1test,
2warnings in18.81seconds, with zero generation/Google mutation during the test.
REST proved a positively observed character and idempotent accumulated counts.
An owned character fixture was created beforehand from an existing image without
image generation; owned fixture cleanup subsequently passed (phase:cleaned), preserving original
character IDs and the fresh source image with zero generations.

Explicit resume reads now require request-project/source-path correlation on
https://flow.google.com through read_project_payload(require_request_project=True).
The actual fixture creator observed4GetProjectContents responses, all with the
selected source path. Five red guard cases preceded17passing combined cases.
Focused core/adapters97passed and CLI-parity/native-SDK compatibility87passed;
Pyright0errors. Full frozen-source gates remain pending. Saved-user voice live
fixture/playback acceptance remains absent; no paid TTS acceptance is inferred.

Final strict response correlation requires exact netloc flow.google.com and
preserves blank query values when validating source paths. Three port/userinfo/
duplicate-blank red regressions preceded20passing transport/resume cases. The
final strict actual SDK BDD passed1test,2warnings in13.49seconds with zero
generations. Final council GO recorded; corrected full frozen-source gates subsequently passed, recorded below.

Final frozen-source R03 catalog-resume gates passed6649tests,5skips,15warnings,
89%coverage in280.10seconds. Prechecks, hygiene, document links, published PII,
mirrors, council, Ruff/formatting and Pyright0errors all passed; council verdictGO.
Actual strict SDK BDD13.49seconds and REST observation BDD18.81seconds passed
with zero generation, and owned fixture cleanup preserved originals/source image.
Publication and deployment follow separately and are not yet claimed. Saved-user
audio fixture acceptance, complete history/cohorts and authoritative reconciliation
remain open; R03 is not declared complete.
