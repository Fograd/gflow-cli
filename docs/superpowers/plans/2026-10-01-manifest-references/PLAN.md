# Manifest References Implementation Plan (#913)

> **For agentic workers:** Run `/gflow:status --feature manifest-references` to find the
> next unchecked task. Implement one task at a time. Run `/gflow:check` before every commit.

**Goal:** a `gflow run --config` row with `"ref": "batch:N"` generates from row N's image,
referencing the image Flow already holds (no re-upload), and the catalog records which
image each generation was made from. Every reference form that cannot be honoured is
refused up front instead of silently dropped.

**Architecture:** orchestration stays in `image_batch.py` (validation, stable dependency
order, outcome model, mapping a row to the existing `ImageRef(name=<media_id>,
display_name=<Flow caption>)`). The transport gains one branch in
`migrated_composer.run_images`: an `ImageRef` with a `display_name` is @-mentioned in place,
no upload, and the `ogiZ0b` submit is aborted unless it carries that media id. No new
request field; `image batch` (stay-mounted path) refuses references; MCP stays exempt.

**Predict verdict:** CAUTION, 8/10 (2026-10-01; all five personas CAUTION, no STOP).
**Scenario:** [SCENARIO.md](SCENARIO.md), 44 scenarios, 22 must-cover.
**Evidence:** [`docs/superpowers/spikes/2026-10-01-batch-ref-dropped.md`](../../spikes/2026-10-01-batch-ref-dropped.md).

**Risk register:**
| Severity | Risk | Mitigation |
|---|---|---|
| Critical | a failed parent leaves children submitted without their reference (#8) | transitive skip with reason; children keyed off the reply, not status (T3) |
| Critical | dependency ordering reshuffles a valid manifest; names and indexes shift (#10, #36) | stable order; identity = row index everywhere (T2, T3) |
| Critical | parent generated but download failed → children wrongly skipped (#35) | `BatchOutcome.images` from the reply, separate from download status (T3) |
| High | caption binds a different image; today detected only after the spend (#15) | abort the mismatched `ogiZ0b` via `page.route` (T5) |
| High | picker searches the whole account library: a re-run binds yesterday's same caption (#40) | **gating spike T0**; design adjusts before T5 |
| High | Enter in the composer submits when the picker is empty (#39) | Enter only when an option is offered (T5), live check (T0) |
| High | a Flow-written caption carries `\n` / `@` / control chars (#19) | sanitise, refuse if changed (T5) |
| Medium | search lag on a fresh generation exhausts retries (#17) | measured ≥5 runs in T0 / T8 |

---

## Delivery

| PR | Tasks | Ships |
|---|---|---|
| **A** | T1 | the silent drop becomes an explicit refusal; the false v0.52.0 record is corrected |
| **B** | T0, T2–T9 | `batch:N` on `gflow run --config`, with persistence and lineage |
| **C** | T10 | local-file references, uploaded once per run |

---

## File structure

### New files
```
tests/test_manifest_refs.py
  parse validation, stable order, outcome/skip model (offline)
tests/features/manifest_refs.feature + tests/features/test_manifest_refs_steps.py
  offline BDD: refusals, skip propagation, naming
tests/e2e/features/manifest_refs_e2e.feature + tests/e2e/test_manifest_refs_bdd.py
  @e2e @e2e_image: live chains on flow.google.com
scripts/dev/spike_batch_ref_dropped.py, spike_mention_existing_media.py,
scripts/dev/spike_batch_ref_existing_media.py
  the measurements behind this plan (already written)
```

### Modified files
```
src/gflow_cli/image_batch.py        validation, stable order, BatchOutcome.images, skip, recording
src/gflow_cli/cli_run.py            help text; reference_entity pre-flight
src/gflow_cli/cli_image.py          image batch: refuse references; help text
src/gflow_cli/api/transports/migrated_composer.py
                                    existing-media branch, sanitise, Enter guard, submit abort
src/gflow_cli/data/recorder.py      (if needed) i2i lineage for run rows
tests/mcp/test_cli_parity.py        "run" exemption reason
docs/USAGE.md, docs/REFERENCE_STRATEGIES.md, KNOWN_ISSUES.md, CHANGELOG.md,
docs/LIVE_VERIFICATION_v0.52.0.md (correction note), website/docs mirror
```

---

## Task 1 — Refuse every reference form, correct the record (PR A)

**What:** `ref` / `reference_entity` in any manifest row is refused before browser work (`run --config` exit 11, `image batch` usage error exit 2),
naming the row and field, until T6 replaces it for `batch:N`. Ships alone.

**Files:** `image_batch.py` (`parse_batch_item_dict`), `tests/test_manifest_refs.py`,
`CHANGELOG.md`, `docs/LIVE_VERIFICATION_v0.52.0.md`, the spike scripts and findings.

**Steps:**
- [x] Red test: each form (`batch:0`, a path, an entity UUID, `reference_entity: "batch:0"`) is refused (`run --config` exit 11, `image batch` exit 2), names row + field, launches no browser
- [x] `parse_batch_item_dict` raises `ConfigurationError` for any non-null `ref` / `reference_entity`
- [x] `image batch` surfaces exit 11 (not `click.UsageError` exit 2) for this error, or the test pins the observed code with a comment (pinned: exit 2, `_as_usage_error`)
- [x] Correction notes: `LIVE_VERIFICATION_v0.52.0.md` row 5 (the PASS could not be produced) and the CHANGELOG #317 entry; CHANGELOG `[Unreleased]` Fixed
- [x] Commit the spike scripts and `docs/superpowers/spikes/2026-10-01-batch-ref-dropped.md`

**Tests created (red):** refusal per form × command; no-reference manifests unchanged (#13).

---

## Task 0 — Gating spike (PR B, before T5)

**What:** measure the four claims T5 rests on. ~8 images, 0 credits. Extend
`spike_batch_ref_existing_media.py`.

**Steps:**
- [x] **#40 picker scope:** measured: project-scoped (control included).  in a **new** project, search a caption that exists only in another project. Found → account-wide search; record it and choose the mitigation (project filter or rely on the T5 abort)
- [x] **#16 negative control:** measured: refused (`WireFormatError`).  mention an unrelated image, return row 0's id → the body check must refuse
- [x] **#17 lag:** 3/3 first-attempt hits so far; ≥5 more in Task 8.  5 runs of the batch-shaped spike; record `mention_miss` attempts per run
- [x] **#39 Enter on empty:** measured: no submit; the dialog stays open (latent retry defect, see T5).  query a caption not yet indexed; confirm whether Enter submits
- [x] Record the readings in the spike doc **before** T5 starts; if #40 is account-wide and no filter exists, stop and revisit the design with the owner

---

- [x] **Found during the gate:** captions collide (#21, observed); binder changed to thumbnail-token identity (spike doc § Gate). Owner informed.

## Task 2 — Validation and stable order (PR B)

**What:** strict parse-time validation and a dependency order that keeps file order.

**Files:** `image_batch.py` (`parse_batch_item_dict`, `resolve_batch_dependencies`), tests.

**Steps:**
- [x] Red tests: #1–3, #5–7, #36, #37
- [x] `ref` matches `^batch:(0|[1-9][0-9]*)$` (other `ref` strings stay refused until T10) — `batch_parent`
- [x] range, self, cycle → `ConfigurationError` (exit 11), not `BatchIntegrityError`
- [x] `reference_entity: "batch:N"` refused; `count > 1` parent refused ("row N makes K images")
- [x] Replace the FIFO topological sort with a stable one — `order_batch_rows`; `reference_entity: "batch:N"` stays refused at parse (T1) (file order, defer a row only until its parent)

**Tests:** must-cover #1, #2, #3, #7, #36, #37; should-cover #5, #6.

---

## Task 3 — Outcome model, identity, skip propagation (PR B)

**What:** rows keep their own identity; children follow the reply, not the download.

**Files:** `image_batch.py` (`BatchOutcome`, `run_one_image_prompt`, `run_sequential_batch`, `render_image_batch_summary`).

**Steps:**
- [x] Red tests: #8, #9, #10, #13, #35, #38
- [x] `BatchOutcome.images: list[GeneratedImage]` set from the reply even when the download fails
- [x] output names, outcome indexes and `--fail-fast` skip rows use `item.index`
- [x] a child whose parent has no `images` is `skipped` with error "parent row N failed", transitively
- [x] a non-`GFlowError` from `download_image` (`ValueError`) is contained per row, not run-fatal
- [x] the results table shows a skipped row's reason; the run exits non-zero when anything was skipped

**Tests:** must-cover #8, #9, #10, #13, #35, #38.

---

- [x] Note for T4: a download failure no longer goes through the generation-failure recorder; T4 records it as generated with a failed transfer (#896 semantics).

## Task 4 — Persistence and lineage (PR B)

**What:** every `run` row is tracked; a referencing row records its input.

**Files:** `image_batch.py` (`run_one_image_prompt` success path), `data/recorder.py` if needed.

**Steps:**
- [ ] Red tests: #31, #31a, #31b, #41
- [ ] successful `run` rows call `record_generated_images` (as `image batch` does, `:945`)
- [ ] a `batch:N` row records `operation_kind="i2i"`, `input_media_ids=[parent media id]`; others stay `t2i`
- [ ] a failed referencing row is recorded as I2I
- [ ] a recorder `DataStoreError` warns and continues; the in-memory handle still feeds the child

**Tests:** must-cover #31, #31a; should-cover #31b, #41.

---

## Task 5 — Transport: reference an existing image, no upload (PR B)

**What:** `run_images` binds an `ImageRef` that carries a `display_name` by @-mention, with the
submit aborted unless it carries the media id.

**Files:** `migrated_composer.py` (`_unported_image_form`, `run_images`, `_mention_by_name`, submit observation), tests.

**Steps:**
- [ ] Red tests: #15, #18, #19, #21, #23, #39
- [ ] `_unported_image_form`: refs **with** `display_name` pass; a bare UUID ref stays exit 36
- [ ] new branch next to `ref_paths`: mention each existing ref, append its media id to `reference_ids`, check the chip count
- [ ] sanitise the caption (strip control chars and `@`, cap length); refuse if changed or empty; empty `display_name` refused on flow.google.com only
- [ ] select the option whose thumbnail token matches the parent's grid tile (`img[data-media-id]`), not the first option; none matches → `ReferenceNotFoundError`
- [ ] on a miss, press Escape to close the picker dialog before retrying (latent defect, gate #39)
- [ ] abort a mismatched `ogiZ0b` with `page.route` before it reaches Flow (keep the observer as the second line)
- [ ] apply T0's #40 mitigation

**Tests:** must-cover #15, #18, #19, #23, #39.

---

## Task 6 — Wire `batch:N` on `gflow run --config` (PR B)

**What:** a child row's request carries `refs=(ImageRef(parent media id, parent display_name),)`.

**Files:** `image_batch.py`, `cli_run.py`, `cli_image.py`.

**Steps:**
- [ ] Red tests: #4, #11, #26, #27
- [ ] T1's blanket refusal is narrowed: `batch:N` accepted by `run`; paths / entities still refused (T10)
- [ ] child request built from the parent's `BatchOutcome.images[0]`; never a `local_path` (no labs re-upload)
- [ ] `image batch` keeps refusing references, pointing at `gflow run --config`
- [ ] `reference_entity` on flow.google.com refused before row 0 submits

**Tests:** must-cover #26, #27; should-cover #4, #11.

---

## Task 7 — MCP surface (PR B)

**What:** no MCP twin: `run` and `image batch` are deliberately exempt (billed, long-running,
no consent path). Mirror axes per `skills/check/SKILL.md` step 1b: none affected.

**Steps:**
- [ ] Fix the `"run"` exemption reason in `tests/mcp/test_cli_parity.py` (#33)
- [ ] Confirm no MCP docstring claims manifest references

---

## Task 8 — E2E (PR B)

**What:** the BDD-bound live test, `@e2e @e2e_image` (images only, 0 credits).

**Steps:**
- [ ] `row 1 references row 0`: both succeed, row 1's submit carries row 0's media id, no `maseQ` upload
- [ ] 3-row chain 2→1→0 (#12) and two children of one parent (#11)
- [ ] catalog: row 1 recorded as i2i with row 0 as input (#31a)
- [ ] run it ≥5 times across sessions; record `mention_miss` counts (#17)

---

## Task 9 — Docs (PR B)

**Steps:**
- [ ] `docs/USAGE.md`: a `gflow run` section (none exists) with `ref: "batch:N"`, the `count: 1` rule, skip semantics, no resume (#42)
- [ ] `run --config` help: point at USAGE, not the planning file `AUDIT_E1 § D`
- [ ] `image batch` help: references not supported there; use `gflow run --config`
- [ ] `docs/REFERENCE_STRATEGIES.md`: `batch:N` as an in-place reference, no upload
- [ ] KNOWN_ISSUES: same-caption fails closed (#21); no resume (#42)
- [ ] CHANGELOG `[Unreleased]` Added; website mirror regenerated

---

## Task 10 — Local-file references, uploaded once (PR C)

**What:** `"ref": "<path>"` → `ref_paths`, each distinct file uploaded once per run and
re-mentioned afterwards.

**Steps:**
- [ ] Red tests: #28, #29, #30
- [ ] resolve against the manifest's directory; `resolve(strict=True)`, `is_file()`, image magic bytes
- [ ] per-run cache `{resolved path: (media_id, display_name)}` scoped to one `run_sequential_batch` call
- [ ] e2e: two rows referencing the same file → one `maseQ` upload

---

## Definition of done

- [ ] All task steps checked off
- [ ] `/gflow:check` green (ruff / format / pyright / pytest ≥ 80% coverage)
- [ ] SonarCloud gate green on each PR
- [ ] `CHANGELOG.md` `[Unreleased]` updated per PR
- [ ] Docs updated (T9)
- [ ] BDD covers every Critical + High scenario in SCENARIO.md
- [ ] e2e run on a live profile and its result pasted in the PR (T8)
- [ ] No `# TODO` without a tracked issue link
- [ ] Deferred items filed: #25 exit-code unification, `--ref <uuid>` port on flow.google.com, `batch:N.k`, resume
