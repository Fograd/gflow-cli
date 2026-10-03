# Derived first-reference image aspect

Scope: implement a shared local approximation for image `auto`, resolving to one of
Flow's five supported explicit ratios. No invented Google enum or backend parity claim.

Predict: CAUTION, 8/10. Architect: pure immutable decision plus bounded file adapter;
Security: decode only caller-resolved local images, no URLs/secrets, refuse oversized
files/pixels and invalid formats before browser activity; Performance: one first-image
probe, no browser round trip; UX: CLI/MCP/HTTP must retain requested and resolved aspect
and policy metadata; Devil's advocate: exact native Auto is unmeasured and this policy
must remain explicitly labeled an approximation. Parent coordinates independent peers.

Scenario matrix: exact five ratios; arbitrary landscape/portrait; scale invariance;
inverted ratios; ties stable; boolean/zero/negative dimensions; oversized/corrupt/file
missing/unsupported images; absent actual reference (character-only invalid); ordered
first-reference wins; explicit aspect stays unchanged; no generation during abort proof.

- [x] Red pure decision and image-file validation tests.
- [x] Implement helper with bounded PNG/JPEG first-reference validation.
- [x] Hand shared contract to CLI/MCP and HTTP owners.
- [x] Capture outgoing explicit aspect in an abort-only reference request.
- [x] Publish truthful spike evidence and scope limitations.
- [x] Focused tests/lint/type checks for owned helper and transport; broader caller review pending.

Generation acceptance is a separate parent-authorized test; abort proof demonstrates
outgoing structure, not Google accepting an image. Existing user image permission does
not permit video/TTS tests.

## Measured image entity transport

Predict CAUTION: exact chip kind+UUID and outgoing correlated project/rows/chunks/vector
must match before allowing Google submission. No string-presence proof; native UI picker
names can collide with media. Preserve preattached media, validate aligned names before
UI, retain video guard and no replay of unknown mutation. Bounded one count 1 image proof
is authorized by parent after guard tests; terminal/download failure does not auto-repeat.
Weighted character image budget requires fresh SDK entity catalog before browser submit
(peer owns caller preflight). Scenario: wrong entity/name/vector/project, entity token only
in prompt, malformed batch, no vector, stale wrong chip, media retained, names misaligned.

- [x] Red parser and orchestration tests for image entities.
- [x] Correlated row8/row10 gate plus entity attachment preserving media.
- [x] Offline guard regression and native abort guard pass.
- [x] One accepted entity image under authorized count 1 budget, checkpoint IDs privately.
- [x] Document outcome; adapter follow-up remains separately authorized and bounded.

## Positional canonical markers (parent-approved extension)

Immutable validated reference_prompt_plan is supplied by the SDK boundary (peer).
Security: ordered native media/entity chunks plus deduplicated vectors must correlate,
not bare text or UUID substrings. Local uploads map logical source IDs to actual Google
media acknowledgements; first-reference order/profile containment remain caller-owned.
Performance: upload once per dedup attachment, compose only after uploads finish;
no extra browser/context/profile. UX: literals retain content and repeated markers retain
position. Unmentioned attachments are prefixed. Unsupported shapes refuse before submit.
Scenarios: duplicate markers, reordered/dropped inline chunk, literal substitution,
extra/missing vectors, stale names, logical/upload identity mismatch, multiline unknown.

- [x] Pure full ordered native prompt guard red→green.
- [x] Structural materialization preserving source spans and unmentioned attachments.
- [x] Native abort-only proof before enabling canonical marker submission.

Historical authentication blocker (before manual restoration): the profile reached Flow's public /about landing and
Google's identity challenge after selecting its exact recorded account. No generation
was submitted, no owned fixture was created, and the one-image permission remains unused.
This sequence does not establish a cause for the authentication state.

After manual authentication, reopening the original profile verified native project
access and owned metadata create/copy/delete. Canonical abort-only probes found one
picker-added ASCII space per committed chip; a structurally verified caret deletion
removes that generated separator before inserting the original literal span. Exact
outgoing chunk verification remains mandatory. No paid image was submitted by these
probes. Final corrected abort and acceptance proof are recorded separately below.

Corrected abort proof passed full positional guard: exact authored literals, repeated
media chips, character chip, deduplicated vectors, and square scalar. A scoped callback
then deliberately aborted before route continuation; the owned fixture was deleted.
The separately authorized one-image SDK acceptance proof passed: 1 BDD in 104.75s,
exactly one submit, decoded 1024×1024JPEG 270277 bytes, private remote checkpoint,
and owned character cleanup. No other generation was attempted. Pro1 was released.

## Public UUID adapter hydration follow-up

The first real CLI canonical-reference invocation refused before image submission
(exit 36): SDK ownership validation retained a bare reference's untrusted/empty
picker metadata. Its uniquely owned character was removed and source images remained.
No additional image was generated. CLI, registered MCP and deployed HTTP acceptance
remain pending their own separately coordinated count-one tests.

- [x] Red regressions show bare UUID hydration, invalid captions and duplicate media
  previously passed unchanged or failed composer eligibility.
- [x] Reuse the same fresh snapshot to populate validated reference captions and
  `in_project`; preserve ordered IDs and exact canonical spans. Refuse missing, blank,
  oversized or ambiguous active-workflow captions and duplicated media identities.
- [x] SDK fault test confirms refusal precedes token mint, checkpoint and submit.
- [ ] Live adapter acceptance after the hydration fix is deployed.

Captions locate picker entries; they do not prove ownership. The native correlated
image guard still verifies actual media/entity IDs and ordered prompt chunks.

Picker eligibility is narrower than the snapshot parser's 4096-character caption
bound: `_picker_query` currently accepts at most 120 characters, strips leading/
trailing whitespace, and refuses `@` plus Unicode control/format and line/paragraph
separator characters. Normalized caption collisions can therefore still refuse at
the picker before submission. Native selected-ID and positional guards remain
mandatory. Adapter live preflight checks this narrower boundary; harmonizing it
with SDK preflight is a separate follow-up, not part of the frozen hydration fix.

Isolated hydration checkpoint verification: 5506 passed, 30 skipped, 15 warnings; 90.62% coverage in 223.67s. All source files match the independently reviewed isolated tree; whole-tree Ruff/strict Pyright and hygiene/docs/privacy/mirror/council gates passed. One pre-dispatch CLI refusal established the need for hydration; this offline gate is not wrapper acceptance.
