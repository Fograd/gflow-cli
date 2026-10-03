# Portable native MP4 ingestion and whole-batch archive

Standing scope: implement useapi Flow capabilities on the self-hosted fork,
including SDK, CLI and MCP surfaces for already measured native media resources.
REST native MP4 ingestion and selected-project whole-batch archive exist; this
work shares the measured operation rather than adding an invented HTTP endpoint.

Predict aggregate CAUTION8 across Architect, Security, Performance, UX and
Devil. A strict true per-request upload-rights assertion is required before any
browser action. A regular bounded MP4 snapshot is identified with ftyp, not
claimed fully decoded;250MiB is a local budget, not Google's published limit.
Fresh project access precedes chooser actions. Private snapshots must be removed
on success, rejection and cancellation.

Native archive is reversible move-to-trash of entire batches. Validate every
requested active owned UUID and actual workflow sibling membership before the
first write. Unknown complete project inventory does not prove batch siblings;
fail closed where membership is absent. Typed unknown errors preserve known
acknowledgements and never replay upload/archive automatically.

Scenarios: false/int/string rights assertion; bad UUID/unsupported host;
nonregular/symlink/FIFO/oversize/truncated/mutating MP4; missing project access;
cancellation/response loss after possible ingestion; known media ID before later
failure; unknown batch siblings/mixed owners/duplicate IDs; partial archive ack;
CLI/MCP signatures and queued payload symmetry; safe literal output and private
paths; actual credit-free synthetic upload/list/archive BDD with owned cleanup.

- [ ] Red bounded file snapshot/rights/UUID and archive-preflight tests.
- [ ] Shared typed SDK methods and nonretryable unknown/partial acknowledgements.
- [ ] Native transport uses validated snapshot and strict pre-request consent;
  original REST path retains documented semantics through the shared helper.
- [ ] CLI and MCP mirrors with explicit reversible scope and safe recovery handles.
- [ ] Offline BDD, six mirror axes and actual SDK/CLI/MCP credit-free probe.
- [ ] Docs, review, whole-tree gates and publication.

No video/TTS generation credits are required. Uploaded synthetic video proves
ingestion/archive, not Veo export, video editing or higher resolution promotion.
