# Scenario: wire manifest references (#913)

Input: predict verdict CAUTION 8/10 (2026-10-01; all five personas CAUTION, no STOP).
Evidence: [`docs/superpowers/spikes/2026-10-01-batch-ref-dropped.md`](../../spikes/2026-10-01-batch-ref-dropped.md).

**Feature.** `gflow run --config` / `gflow image batch` rows may carry `"ref"` and
`"reference_entity"`. Today both are parsed and silently dropped. After this change:

- `"ref": "batch:N"` makes row N's generated image a reference, by the handle Flow's reply
  returns (`ImageRef(name=<media_id>, display_name=<Flow caption>)`), with no upload. On
  flow.google.com the composer @-mentions the caption, and `_image_body_problem` requires
  the `ogiZ0b` body to carry the media id.
- `"ref": "<local path>"` is uploaded once per run and reused (a later phase).
- `"reference_entity"` follows the existing `reference_entities` path. That path is not
  ported on flow.google.com: refused, exit 36.

**Surfaces.** `gflow run --config` is the per-prompt path and is reachable on flow.google.com.
`gflow image batch` is the stay-mounted path, refused on flow.google.com
(`ui_automation.py:3370`). Both are MCP-exempt.

## Coverage map

| Dim | Active? | Why |
|---|---|---|
| D1 Auth | yes | session expiry mid-chain strands dependents |
| D2 WAF/reCAPTCHA | light | extra `as29s` picker searches per row; no extra token mint (measured) |
| D3 Selectors | yes | reuses the composer `@` picker (`PICKER_OPTION`, `MENTION_CHIP`); caption matching |
| D4 Batch | **core** | ordering, failed parents, `count > 1`, file naming, no resume |
| D5 Concurrency | light | `run` is sequential (`concurrency` default 1); page pool FIFO |
| D6 Data layer | yes | successful `run` rows are not recorded (pre-existing); failed-row records |
| D7 Errors | yes | exit codes differ between the two commands today |
| D8 Paths | yes | local `ref` paths in a JSON manifest, Windows |
| D9 Transport | yes | wire body check; the reference must reach `ogiZ0b` |
| D10 Headless | no | no new launch behaviour |
| D11 Input validation | **core** | every malformed reference form |
| D12 Observability | yes | new events, no prompt or path leakage |
| D13 MCP | light | both commands exempt; the exemption reason text is wrong |

## Scenario table

| # | Dim | Scenario | Sev | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D11 | `ref: "batch:N"` with N out of range, `batch:-1`, `batch:x`, `batch:` | High | refused at parse, exit 11 (`ConfigurationError`), names row and value, no browser | Unit |
| 2 | D11 | `batch:N` with N == own index | High | refused at parse, exit 11 | Unit |
| 3 | D11 | cycle (0→1→0) or longer (0→2→1→0) | High | refused at parse, exit 11 (not `BatchIntegrityError`, which is unmapped and exits 1) | Unit |
| 4 | D11 | forward reference (row 0 refs `batch:2`) | Medium | allowed; stable order runs 1, 2, then 0 (a row is deferred only until its parent ran) | Unit + BDD |
| 5 | D11 | `reference_entity: "batch:N"` (the alias the resolver honours today) | Medium | refused, exit 11: "use `ref` for an earlier row" | Unit |
| 6 | D11 | `ref` is a list, number, or empty string | Medium | refused, exit 11 (a list is not silently joined) | Unit |
| 7 | D4 | parent row has `count > 1` | High | refused at parse, exit 11: "row N makes K images; `batch:N` needs `count: 1`" | Unit |
| 8 | D4 | parent row fails with `--continue-on-error` (**the default**, `cli_run.py`) | **Critical** | dependents `skipped` with error "parent row N failed", never submitted without the reference; transitive (grandchildren skipped) | Integration |
| 9 | D4 | parent row fails with `--fail-fast` | High | batch stops as today; skipped rows carry their **own** index (today `index=skip_idx` is the loop position) | Integration |
| 10 | D4 | dependency order differs from file order | **Critical** | output names (`prompt_{index}`), outcome indexes and the results table keep the **row's** index, not the loop position | Unit + Integration |
| 11 | D4 | two rows reference the same parent | Medium | both bind the same media id; parent generated once | Integration |
| 12 | D4 | 3-row chain 2→1→0 | Medium | runs 0,1,2 in order; each binds its direct parent | E2E live |
| 13 | D4 | no references at all | High | behaviour byte-identical to today (order, names, results) | Unit (regression) |
| 14 | D4 | a row's own references plus a manifest `count` | Low | a child with `count > 1` is fine (only parents are restricted) | Unit |
| 15 | D9 | caption bound a different image (prefix or similar caption) | High | `_image_body_problem` refuses to report (`WireFormatError`, exit 7, `migrated_composer.py:2747-2750`); quota already spent; dependents skipped | Integration + one live negative control |
| 16 | D9 | negative control: mention an unrelated image, return row N's id | High | body check refuses. Proves it is a real discriminator, not a substring coincidence | E2E live (spike) |
| 17 | D3 | fresh generation not yet indexed by the picker search | High | existing retries (`FRAME_SEARCH_ATTEMPTS`) find it; miss → `ReferenceNotFoundError` naming the caption; measured across ≥5 runs, `mention_miss` counts logged | E2E live |
| 18 | D3 | reply `display_name` empty or None, **on flow.google.com** (labs binds by UUID via `_attach_image_uuid_refs` and its agentic driver never sets `display_name`, `agentic.py:908`; do not refuse there) | High | the row refuses before submit: "Flow returned no caption for row N; cannot reference it" (no blind search) | Unit |
| 19 | D3 | caption contains `\n`, `@`, control chars, emoji, or is very long | High | sanitised (strip control chars and `@`, cap length); if sanitising changed it or emptied it, refuse rather than search a different string | Unit |
| 20 | D3 | caption truncated with "…" in the picker | Medium | the search uses the full reply caption; body check is the arbiter | E2E live (observe) |
| 21 | D3 | two rows produce the same caption | Medium | fails closed via the body check; documented limitation | Integration |
| 22 | D9 | mention chips already attached by `ref_paths` when the existing-ref mention runs (unreachable from a manifest, whose `ref` is one string; reachable only from a future `--ref` caller) | Low | the existing-ref branch does not clear prior chips; chip count == total references | Integration |
| 23 | D9 | `_unported_image_form` narrowing | High | refs **with** a `display_name` pass; a bare UUID `--ref` on flow.google.com is still refused exit 36 (no regression of the general rule) | Unit |
| 24 | D1 | auth expires mid-chain | Medium | the failing row reports `AuthExpiredError` (exit 3); dependents skipped; no silent text-only generation | Integration |
| 25 | D7 | same malformed manifest via `run` vs `image batch` | Medium | both exit 11 (today `image batch` maps to `click.UsageError`, exit 2: unify or document) | Unit |
| 26 | D7 | `reference_entity` on flow.google.com | High | exit 36 **before row 0 submits** (no quota spent on earlier rows) | Integration |
| 27 | D4 | `image batch` (stay-mounted path) with any reference | High | refused at parse with a clear message pointing at `gflow run --config`; the stay-mounted path is not taught references (unobservable on labs) | Unit |
| 28 | D8 | local `ref` path relative, absolute, Windows `C:/x.png`, `C:\\x.png`, spaces/Unicode | Medium | resolved against the **manifest's directory**; must exist, be a file, and be an image (magic bytes); symlink resolved strictly | Unit (phase 2) |
| 29 | D8 | local `ref` path to a non-image or a secret file (`~/.ssh/id_rsa`) | High | refused at parse, exit 11, before any upload | Unit (phase 2) |
| 30 | D4 | same local file referenced by several rows | Medium | uploaded once per run; later rows mention the cached upload; cache lives exactly one run (one project) | Integration (phase 2) |
| 31 | D6 | successful `run` rows are not recorded in the catalog (pre-existing: `run_one_image_prompt` records failures only, `image_batch.py:533`) | **High** | **in scope** (owner, 2026-10-01): every successful `run` row is recorded via `record_generated_images`, as `image batch` already does (`:945`) | Integration |
| 31a | D6 | reference lineage is not recorded: `image batch` hard-codes `operation_kind="t2i"`, `input_media_ids=[]` (`:945-955`); `OperationAssetRole.REFERENCE` exists but is unused | **High** | a `batch:N` row is recorded as `i2i` with `input_media_ids=[parent media id]`, so the catalog answers "which image was this made from?"; a row without references stays `t2i` | Integration |
| 31b | D6 | recording fails (DB locked, `DataStoreError`) on a parent row | Medium | warn and continue, as the existing recorder path does; the in-memory handle still feeds the child (persistence is tracking, not control flow) | Integration |
| 32 | D12 | new log events | Medium | caption and paths not logged in full (file name only; caption length or hash); no `ogiZ0b` body logged | Unit |
| 33 | D13 | MCP | Low | both commands stay exempt; fix the `"run"` exemption reason (`test_cli_parity.py:108` says "chain-manifest runner") | Unit |
| 34 | D2 | references add picker searches | Low | ≤ `FRAME_SEARCH_ATTEMPTS` `as29s` per referencing row; no extra token mint | — (measured) |
| 35 | D4 | parent generated, but its **download** failed (CDN reset, #896 style): generate and download share one `try` (`image_batch.py:509-519`) | **Critical** | the outcome keeps the reply's images separately from the download result; the child still runs, because the media exists in the project. A `ValueError` from `download_image` (not a `GFlowError`) must not escape and abort the run without a results table | Integration |
| 36 | D4 | `resolve_batch_dependencies` reorders an already-valid manifest (`[0, 1→0, 2]` → `[0, 2, 1]`, measured) | **Critical** | stable order: file order, deferring a row only until its parent has run. Replace the FIFO queue | Unit |
| 37 | D11 | indexes `int()` accepts: `"batch: 1"`, `"batch:+1"`, `"batch:01"`, `"batch:1_0"` (→ 10), non-ASCII digits (measured) | High | match `^batch:(0\|[1-9][0-9]*)$` exactly; anything else exit 11 | Unit |
| 38 | D7 | the results table prints `(not attempted)` for a skipped row and ignores `outcome.error` (`render_image_batch_summary`, `:1276-1278`) | High | a skipped row shows "skipped: parent row N failed"; its exit code is non-zero overall when anything was skipped | Unit |
| 39 | D9 | Enter pressed in `_mention_by_name` when the picker offered nothing (fresh caption not indexed): Enter in the composer can submit (`send_prompt` warns, `:2374`) | High | press Enter only when the picker lists at least one option; otherwise retry the search. **Live check** | E2E live |
| 40 | D3 | picker search scope: `run` creates a new project each time; if the `@` search spans the account library, a re-run finds yesterday's same caption first | High | measure (spike) before building. If account-wide, the body check refuses after the quota is spent; mitigation: run the search with the project filter, or abort the submit (see improvement 1) | Spike (live) |
| 41 | D6 | a failed referencing row is recorded as T2I (`record_failed_operation_safe(mode=OperationKind.T2I)`, `:539`) | Medium | recorded as I2I with the parent as input | Integration |
| 42 | D4 | no resume: `run` allows up to 50 prompts (`MAX_PROMPTS`), one early failure skips a whole chain, and a re-run re-bills every parent | Medium | documented limitation in v1; resume needs `ref` by media id + caption across runs (future) | — (doc) |

## Must-cover before merge (Critical + High)

1–3, 7, 8, 9, 10, 13, 15, 16, 17, 18, 19, 23, 26, 27, 31, 31a, 35, 36, 37, 38, 39, 40 (and 28–30 with the local-path phase).

## Deferred (log as issues, not blockers)

- 25: unify `image batch` parse errors to exit 11.
- Porting `--ref <uuid>` on flow.google.com through the same mention-by-caption branch
  (it needs a caption, which a bare UUID does not carry).
- `batch:N.k` for a `count > 1` parent, if asked for.

## Suggested BDD scenarios

```gherkin
Feature: Manifest references
  # Offline (parsing, ordering, skip propagation): tests/features/test_manifest_refs_steps.py

  Scenario: a reference to a missing row is refused before any browser work
    Given a run config whose row 1 has ref "batch:5" and only 2 rows
    When I run the config
    Then it exits 11 naming row 1 and "batch:5"
    And no browser was launched

  Scenario: a parent with several images cannot be referenced
    Given row 0 has count 2 and row 1 has ref "batch:0"
    When I run the config
    Then it exits 11 saying row 0 makes 2 images

  Scenario: a failed parent skips its dependents
    Given row 1 references row 0, row 2 references row 1, and row 0 fails
    When I run the config with continue-on-error
    Then rows 1 and 2 are skipped with "parent row" in their error
    And neither was submitted

  Scenario: dependency order keeps each row's own name
    Given row 0 references row 1
    When I run the config
    Then row 1 runs before row 0
    And row 0's files are named prompt_0_*
```

```gherkin
@e2e @e2e_image
Feature: Manifest reference to an earlier generated image
  # Live: tests/e2e/test_manifest_refs_bdd.py

  Scenario: row 1 references row 0's image without uploading it
    Given a run config whose row 1 has ref "batch:0"
    When I run it on a profile served flow.google.com
    Then both rows succeed
    And row 1's submit carries row 0's media id
    And no upload was made during row 1
```

## Known-issues cross-reference

- KNOWN_ISSUES "Video duration control is absent" and the #792 re-upload rule: the #792
  rule (uploads are run-unique so a re-run never binds a stale look-alike) is respected.
  `batch:N` binds only an image this run generated, by its reply media id, verified on
  the wire.
- `image batch` unported on flow.google.com (`raise_if_migrated(at="image_batch_unported")`):
  unchanged; references there are refused at parse (#27).

## Corrections from the second-pass review (2026-10-01)

- Only `run` downloads each row before the next; `run_manifest_image_batch` downloads
  after all rows generated. The design keys children off the **reply**, not the download.
- `image batch` exits **1** at runtime on flow.google.com (no `GFlowError` handler reaches
  it), not 36: #25 and #27 pin the observed code.
- Leftover chips between rows: not a gap. After a success the page is parked on
  `about:blank` (`ui_automation.py:3152`); after a failure the park is deferred and done
  before the next row (`:3112`). Each row reopens the editor. A Flow-side composer draft
  restored on reload is unmeasured (Low).

## Design improvements adopted

1. **Abort, don't just observe.** Check the `ogiZ0b` body with `page.route` and abort a
   mismatched submit before it reaches Flow, so #15 / #40 fail **before** quota is spent.
   Today `_image_body_problem` runs in an `on_request` observer (`:2743`).
2. **`BatchOutcome.images`.** Carry the reply's `GeneratedImage`s on the outcome and key
   children off them, not off `status` (fixes #35).
3. **Labs: no local fallback for `batch:N`.** Never pass a `local_path` with a `batch:N`
   `ImageRef`; the labs fallback would re-upload a duplicate.
