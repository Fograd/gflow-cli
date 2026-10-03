# Native and managed REST image inputs

**Goal:** REST image generation accepts owned unregistered native UUIDs and
ordered mixed managed/native reference slots, including first-native Auto.
Fresh URL/download lookup remains the second R02 task; this does not complete R02.

**Architecture:** Extend shared image DTO/codec with optional local_ref_ids paired
with decoded ref_paths. Preserve the immutable ordered canonical plan; native refs
are a filtered ordered subset, and uploaded local aliases bind only acknowledged
media IDs. Combine both binding maps before canonical prompt materialization.
REST creates aliases/contained paths from its own registry, never caller paths.
Unknown native IDs require explicit configured email and selected/default project.
Auto native dimensions resolve inside the serialized selected-account worker.

**Predict:** GO with conditions (five independent persona assessments).
Architect GO: small additive DTO extension, shared plan/binding map.
Security CAUTION8 resolved by server-owned path/alias records, explicit account,
fresh typed ownership before upload/mint, guarded outgoing IDs, no write replay.
Performance GO8: current bounded grid; no native re-upload; preflight before uploads.
CLI/MCP UX GO8: codec round-trip and consistent order; no hidden refs-first merge.
Devil's Advocate CAUTION resolved by pre-upload native/caption/budget validation
and preserving known acknowledged-upload handles on later failure.

## Tasks
- [x] Red tests: DTO/codec mixed mapping, order/repeats, missing/overlap/reordered aliases.
- [x] Shared DTO/plan validation and codec; preserve old pure-local/native callers.
- [x] Composer merges native/upload bindings in plan order; preflight before upload.
- [x] Public CLI/direct+queued MCP mapping and first-reference Auto maintain order.
- [x] REST explicit-account native routing, typed queue inputs/private worker and Auto.
- [x] Tagged no-submit adapter BDD, semantic mirrors, docs and required gates.
- [ ] Pinned review, publish/deploy and runtime capability checks.

## Definition of done
Explicit same-account/project native routing with fresh ownership; managed paths
remain contained and decoded. All image IDs partition plan slots exactly once,
native/local overlap is refused, and repeated markers retain spans/one attachment.
Only acknowledged upload IDs enter outgoing native wire. Wrong IDs refuse before
dispatch. First-reference Auto never falls back to another source.
Do not claim accepted generation from parser/attachment proof; final R12 remains.

## Separate remaining R02 scope
Fresh protected asset URLs/thumbnail/download require measured typed native
URL contracts and bounded trusted byte fetching. No synthetic Store asset,
guessed composite identifier or uploaded/generated parser conflation.

Progress: the positive interleaved codec regression failed on old mixed-mode refusal.
Shared DTO/plan/codec now passes the initial83-test focused matrix; production
composer and REST remain unchanged and mixed generation is still guarded.
Next: add composer binding-merge/wire negatives before enabling mixed inputs.

The expanded core matrix passes87tests in0.41seconds. A new composer regression
fails at the existing mixed-input transport gate, confirming the next integration
point. The intended binding map is native-first/upload-ack/native-last in logical
slot order, with public local aliases never sent as Google media IDs. Before
enabling the transport, cover malformed partitions, safe captions and retained
upload acknowledgements on partial failure/cancellation. No R02 changes are
published or deployed yet; production source remainsfd22da6a (docsHEADd3f99c99).

Composer binding merge now passes the63-test prompt/picker/marker suite in1.30seconds;
native tokens are reacquired after toolbar uploads and submitted ID order follows
the original plan. Partial-upload acknowledgement recovery, public mirrors and
REST/native Auto wiring are still required before publishing or deploying R02.

Pre-enable review found a further concrete upload gap: toolbar upload currently
extracts _first_uuid from the acknowledgement instead of a project/file-correlated
typed upload result. Measure the actual acknowledgement contract or verify the
returned active owned image against the unique requested upload caption before
binding it. Retain acknowledged IDs if any later upload, rediscovery or composition
fails, without replay. This is required by the existing preflight/ack invariant;
current mock mapping tests do not establish it. Do not publish the mixed path yet.

Latest focused sweep:267passed in29.95seconds across migrated composer/images,
native prompt/picker, mixed codec, marker and ownership matrices. Strict Pyright
passes after expressing runtime alias type validation through cast(object).
The next unfinished work is upload acknowledgement correlation/recovery, followed
by public input ordering and explicit-account REST/private-worker/native Auto.
Production remains the reviewed R01 code; this draft has not been committed.

Current progress: explicit caller-order helper is wired into CLI preflight and
generation, plus MCP direct/queued payloads. Tests53(shared slots/codec) and52
(public task modes/Auto) passed. Upload ack decoding now uses measured flat
media/project fields; nine decoder regressions failed first. Corrected upload
fixtures use the same synthetic project UUID as their acknowledgement, rather
than p1;194affected tests passed in29.01seconds. Ruff/format/Pyright are clean.
Next: correlate the acknowledgement to the dispatched file/request and retain
known upload IDs on partial upload, rediscovery or composition failure. Then wire
REST native selection/private-worker/Auto and finish public documentation/live
proof/gates. No R02 draft has been published or deployed.

Latest development: REST explicit-account native/mixed routing is implemented
with strict ordered source records, current registry owner/MIME/path checks and
selected-account native-first Auto in the private worker. Affected641tests passed
in45.02seconds;14REST boundaries passed in0.96seconds including default Auto and
full-worker resolver failure preventing generation. Ruff/Pyright passed.
Chooser request/response association and partial upload/binding handle recovery
are now implemented; cancellation preserves existing native recovery metadata.
No R02 publication/deployment. Next: live bounded no-submit correlated upload and
binding proof, public API/help documentation, final gates and pinned review.
Fresh native URL/download lookup remains the separate second half of R02.

Live evidence changed the upload action: the18.29second tagged probe returned
HTTP200 with a nested response, contradicting the flat-only decoder assumption.
Its exact typed synthetic identity was inspected and archived. The19.74second
schema-capture probe retained a private response and archived its fixture in
cleanup. Fresh project metadata correlates nested media/project/workflow fields
and exact caption; the image arm has JPEG MIME and48x32 dimensions.
The corrected nested decoder passes that actual private response, with ten new
red boundary regressions before implementation. Corrected live binding/gates are
still required; this does not consume a paid generation allowance.

Corrected live upload/owned-identity/canonical-binding/archive BDD passed once
with two warnings in39.95seconds, with zero observed generation requests.
Decoder/composer/native-prompt169tests passed in28.95seconds and Pyright passed.
Composer/public mapping/REST implementation tasks are now checked; full required
gates, semantic documentation sweep and pinned publish/deploy review remain.

First complete sweep:7failed/5924passed/5skipped/15warnings,186.59seconds,
88.29%coverage. All seven failures are migrated i2v BDD fixtures requesting p1
while their toolbar acknowledgement names the synthetic project UUID. Correct
the requested project/expected route/result together; preserve picker/negative
and no-submit assertions. Repeat full required gates before committing R02.

Complete corrected sweep5932passed/5skipped/15warnings180.05seconds,89.00%.
Pinned review D1/D3/D8/D15 GO; D2/D4/D6/D12/D14 CAUTION on acknowledged ID
lost if listener removal throws before returning upload binding. Two new
regressions failed, then the minimal current/earlier handle preservation fix
passed33targeted tests in1.20seconds and Pyright. Final gate and scoped
cleanup re-review remain before publication.

Final source gate:5934passed/5skipped/15warnings206.68seconds,89.00%.
All mechanical/doc/site/memory/61CLI-MCP/Ruff/format/Pyright gates passed.
Three scoped peer reviews GO; the cleanup CAUTION is resolved and re-reviewed
on treea27cfdf2.27-file privacy scan foundzero configured keys/private IDs.
Next unchecked task: commit, atomically publish fork refs, deploy with idle
queues and verify authenticated REST/MCP capabilities. R02 fresh URLs remain.
