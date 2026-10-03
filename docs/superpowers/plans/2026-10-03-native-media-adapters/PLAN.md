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

- [x] Red bounded file snapshot/rights/UUID and archive-preflight tests.
- [x] Shared typed SDK methods and nonretryable unknown/partial acknowledgements.
- [x] Native transport uses validated snapshot and strict pre-request consent;
  REST MP4 uploads now require exact true consent before enqueue, a documented fork strengthening.
- [x] CLI and MCP mirrors with explicit reversible scope and safe recovery handles.
- [x] Offline BDD, six mirror axes and actual SDK/CLI/MCP/HTTP credit-free probes.
- [x] Docs and independent source/recovery reviews; full offline regression5,612passed/28skipped/90.75% in212.90s.
- [x] Published sourcecheckpoint c03c1fe3 to both fork branches; clean CC LXC fast-forward, API/MCPactive, fresh authenticated project-access healthOK, actual MCP24tools/newmedia schemas and MP4missing-consent422 verified without generation.

No video/TTS generation credits are required. Uploaded synthetic video proves
ingestion/archive, not Veo export, video editing or higher resolution promotion.


Historical isolated offline checkpoint: 100 focused SDK/CLI/MCP/HTTP/projection/parity cases passed in 5.14s, then three native-worker cases passed. Registered MCP coercion was reproduced with ordinary bool annotations and fixed using StrictBool; six registered-tool negative validation cases reject false/int/string before profile/service. Scoped Ruff and strict Pyright pass. Source methods preserve acknowledged handles over snapshot cleanup, checkin and client teardown failures; cancellation remains cancellation.

Live synthetic BDD scaffolding has explicit e2e/free-resource tags, one selected surface/budget and a persistent exclusive allowance. It uses registered MCP protocol, records early private acknowledgement checkpoints, and never replays an attempted archive during cleanup. Default collection deselects four cases; explicit E2E selection without credentials skips four. SDK synthetic lifecycle passed in 54.80 seconds and public CLI lifecycle in 57.56 seconds, with originals preserved and no generation/replay. Registered MCP protocol lifecycle passed in 67.96 seconds with originals preserved and no generation/replay; its isolated server was stopped. Corrected-prefix HTTP lifecycle passed in 51.86 seconds: exactly one completed upload job and one completed native archive job, originals preserved, no generation/replay. The earlier wrong-base 404 attempt created zero jobs and its allowance was preserved separately. All four public surface lifecycle proofs passed; final full regression remains pending the root coordinator. No paid generation was run.
