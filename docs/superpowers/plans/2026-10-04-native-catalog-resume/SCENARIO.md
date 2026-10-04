# Catalog resume and observation scenarios

Controls: reject empty, duplicate, malformed or more-than20project UUIDs before
lease. catalog_project_ids requires include_catalogs=True; account cursor or
all_pages/max_pages traversal conflicts refuse. Preserve caller order and
max_projects bounded selection; remaining IDs resume enrichment without skipping.
Default project discovery/catalog behavior is unchanged when IDs are absent.

Read each explicitly selected owned project through the existing fresh payload
codec. Preserve attached origins and selected attachment scope without widening
ownership. No absent row proves deletion; no catalog cache authorizes GetMedia,
generation references or mutation. SDK/CLI/direct MCP/privateworker/REST controls
and return shape must agree; local mode refuses native resume controls.

Durable REST merge_catalogs accepts only allowlisted stable project/character/
saved-user audio/workflow metadata within the exact profile/configured account.
Empty projects are recorded; bundled system presets and URL/prompt/caption/cursor
fields never persist. Cross-scope/identity conflicts roll back the whole merge;
prior missing observations are retained, completeNone.

Actual free BDD must prove bounded ordered resume, cache accumulation and absence
retention, confidential-field exclusion, zero generation/Google mutation and
fixture preservation. No mocked or plan-only result claims live acceptance.
Focused offline regression, mirror/link/PII checks and final gates precede shipping.

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
