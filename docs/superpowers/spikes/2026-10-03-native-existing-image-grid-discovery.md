# Existing-image grid discovery: bounded no-submit investigation

Status: offline plan; browser observation pending its explicit exclusive lease.
No image/video/TTS generation, token mint, solver, upload or entity mutation is
part of this discovery. The three additional adapter image allowances remain unused.

## Observed problem and existing evidence

Actual CLI invocation 3 passed fresh native image/entity ownership preflight, then
refused before Generate because its requested image was not found in the editor
DOM grid. The registered image exists in the same project's active native snapshot;
its local managed file decodes, and its 24-character caption passes picker syntax.
The owned test character was deleted and both source images remained active.

The earlier SDK canonical grounding proof accepted one image using a recent seed
reference. This does not establish that older registered references are discoverable.

Source inspection (not a browser finding):

- `migrated_composer.py::_GRID_TOKEN_JS` scans only currently rendered
  `img[data-media-id]` elements and requires an `/asb/<token>` source URL.
  A missing DOM tile and a present tile with an unrecognized source URL both
  currently become the same empty-token failure.
- `await_existing_references` performs one DOM scan. It does not inspect grid
  pagination, virtualized scroll containers, search/filter state or asset-detail
  responses. `reference_existing` retries by reloading the same editor for up to
  90 seconds, checked after each attempt; a scan can overrun the nominal budget.
- Grid discovery precedes `apply_image_settings`. Whether current mode/filter
  state changes which media render is unmeasured.
- Canonical materialization scans the grid again after initial reference binding.
  Any fix must preserve identity availability across that second scan or safely
  retain an already validated binding, not discard the ownership guard.
- The earlier `2026-10-01-batch-ref-dropped.md` spike measured same-caption options
  selected by an exact grid-thumbnail token, backed by corresponding RPC IDs.
  It explicitly left virtualization for larger projects unmeasured. The current
  SDK caption-ambiguity refusal is conservative; removing it requires separate
  current-session evidence that identity selection still works.

## Architect / Security / Performance prediction

CAUTION: investigate, then implement only a measured discovery path. Active native
ownership is necessary but is not permission to select another matching caption or
silently upload a replacement. Keep actual media IDs, prompt literals and correlated
native submit guards unchanged. Caption/thumbnail metadata is a locator, not ownership
proof. Signed thumbnail URLs, opaque tokens and account/project IDs stay in private
captures and never public documentation or normal error strings.

A bounded scroll or exact native detail-token lookup could avoid ineffective reloads,
but neither is assumed to work. Prefer one native snapshot reused by the caller over
repeated account scans. Fail closed if an identity/token join is ambiguous, the
response shape changes, or the viewport cannot safely expose the requested asset.

## Probe sequence and bounds

1. Check the production queue is idle, acquire the normal original profile lease,
   and install a route guard allowing only measured metadata/read RPCs. Block all
   generation/upload/entity mutation and unknown writes; no production submit helper
   is called. Use the existing `_spike_common` bootstrap/ProfileLease machinery.
2. Reconstruct the actual caller sequence in one `FlowApiClient`: fresh native
   ownership snapshot, return the checked-out page, then check it out and call
   `ensure_editor`. Compare the older registered image and recent seed image by
   exact private IDs. Record active image/workflow membership, never infer image
   kind from captions or missing prompts.
3. Take structural DOM measurements: total media images, exact target attribute
   presence, source URL path family and token presence, bounding-box visibility,
   scrollable ancestry, filters/tab selections and pager affordances. Count/token
   equality booleans are sufficient in public evidence. Do not dump full HTML,
   request bodies, cookies, credentials or signed URLs publicly.
4. If a tile exists but the current parser misses its source, inspect that actual
   source structure and correlate with its native media identity. If it is absent,
   inspect the observed grid's real scroll/pager controls. Try at most six bounded
   scroll steps in that identified container; stop on no progress or end-of-list.
   Measure newly rendered IDs and both targets after every step. Do not guess a
   selector or click arbitrary controls merely named "Next".
5. One editor reload at most, then repeat the target measurements. Observe only
   known read-only RPC structure/cursor presence; a repeated reload is not evidence
   of pagination. A safe exact-ID media-detail read may be compared if its existing
   measured contract yields a thumbnail token tied to that same ID/project.
6. Open the native image `@` picker without Generate. Compare both safe caption
   searches and option tokens against exact target identities. Close the picker
   and clear only the test prompt. No Enter outside the known picker is allowed.
   Separately record whether query options include the requested image even when
   its grid tile is virtualized; do not bind by caption alone.
7. Overall metadata probe deadline: 180 seconds, including one navigation/reload.
   Each read has its existing bounded transport deadline. Always close the normal
   managed client, report no submitted generations, and explicitly release lease.
   If a login challenge, unknown control or unexpected mutation appears, stop.

## Gate for implementation and adapter retry

A discovery fix needs a reproducible identity join, a red regression matching the
actual missing-tile/token condition, negative tests for wrong project/media/token,
bounded progress/deadline tests, and unchanged canonical positional/no-replay guards.
No production edits or new image requests are justified solely by this offline plan.
Basic CLI, registered MCP and deployed HTTP acceptance remain pending. A no-submit
proof must precede any separately authorized count-one adapter invocation.

## Bounded native observation

The explicitly leased no-submit probe completed in one normal client. The queue
was idle first; both exact private target IDs were active typed native images.
The caller sequence was fresh project snapshot, page check-in, page checkout and
editor readiness. Unknown POSTs and all unallowlisted RPCs were aborted; these
blocked requests were not classified as telemetry or safe writes.

Both older registered and recent SDK targets were present in the initial rendered
DOM, each with an `/asb/` thumbnail token recognized by the existing parser. The
older image was below the viewport while the recent image was visible. One observed
scrollable grid DIV had a 720-pixel viewport. Across at most six bounded scroll
steps, rendered image counts changed from 24 to 25, then 19 and 16. The recent
image disappeared from the DOM near the lower end while the older image remained.
One editor reload restored both initial target/token observations. This directly
shows virtualized membership; viewport invisibility alone does not prevent token
parsing when the tile remains mounted.

This probe did **not** reproduce the earlier CLI refusal or establish its timing
cause. No picker was opened, no reference was bound and no caption ambiguity was
relaxed. No generation, upload, entity mutation, solver task or token mint was
requested. The managed client closed and the exclusive profile lease was released.
Private structural evidence is retained outside Git; no signed tokens or IDs are
published here. The additional three image allowances remain unused.

A potential follow-up is bounded target-aware grid readiness/scroll discovery,
retaining an exact-ID validated token across subsequent canonical materialization
and failing closed on changed ownership or ambiguous tokens. This is a proposal,
not an implemented fix: delayed initial mounting and picker option identity still
need a corresponding no-submit observation and meaningful regression before a
new paid adapter attempt. The current fail-closed ownership/literal/UUID guards
remain intact; Google feature absence is not inferred from the earlier refusal.

## Fixture-aware observation and capture limits

A separately authorized free metadata probe added one unique temporary character
by copying the existing recent seed image, distinct from the older direct reference.
Exactly one correlated create, copy and cleanup write was allowed; generation,
upload and unknown writes were blocked. The acknowledged character identity was
checkpointed before later discovery. Cleanup verified removal of the owned fixture
and preservation of every originally active media identity. No generation or solver
budget was used, and the original managed profile lease was released.

Fresh shared ownership preflight passed. Both exact target grid tokens remained
available before fixture creation, after creation and immediately after the
reference-binding helper failed. Mounted grid count changed from 24 to 23 and
scroll height from 3275 to 3341, with scrollTop zero. This run does not support the
hypothesis that the character copy displaced the requested target from mounted DOM.
It also does not reproduce the earlier CLI failure.

The helper returned `UiSelectorDriftError`, not `ReferenceNotFoundError`. An
immediate post-helper scan still recognized both tokens, but no explicit second
`await_existing_references` call was made. The capture stored only the exception
class and aggregate 339 blocked POST requests, not traceback frames or per-RPC
frequencies. Consequently it cannot establish whether the failure happened in
settings or picker binding, nor classify the blocked dependencies. They must not
be called telemetry. The earlier no-fixture request-name capture is a different
run and cannot supply missing fixture-run frequencies.

Before another browser attempt, instrumentation must retain safe function/line
frames, fixed drift fields and method/RPC-name counts in private evidence. No
source change, guard relaxation, generation retry or inferred Google feature
absence follows from this incomplete classification. Paid CLI/MCP/HTTP image
acceptance remains pending, with all three additional allowances unused.
