# Manifest `ref` / `reference_entity` are dropped, all forms (#913) — 2026-10-01

**Question.** Does a manifest row's `ref` / `reference_entity` reach Flow, on the
surfaces that parse manifests?

**Setup.** `develop` @ 773f6ef9, Windows 11, profile `ci-probe`, host served
`flow.google.com`. Script: `scripts/dev/spike_batch_ref_dropped.py`. Signal:
`migrated.references_attached` (`migrated_composer.py:2073`). Cost: 4 images of quota,
0 credits.

## Observed

| Arm | Result |
|---|---|
| control: `image i2i --ref <local.jpg>` | `references_attached` fired once (then an unrelated 30 s API deadline, exit 9): the signal works |
| `image batch` (3 rows) | exit 1 before any row: `raise_if_migrated(at="image_batch_unported")`, `ui_automation.py:3370` |
| `run --config` (same 3 rows) | **exit 0, 3 images saved, `references_attached` 0** |
| offline capture of the request `run_one_image_prompt` builds | `refs=()`, `ref_paths=()`, `reference_entities=()` for `batch:0`, `./cat.png` (nonexistent, not rejected) and an entity UUID |

The spike's "submits" counter read 0 because it counted the video event name
(`migrated.submit_clicked`); that is a defect in the spike, not a finding. The saved images
show the rows ran.

## Reading

- **Wider than #913 as filed.** Every form is accepted and dropped, not only `batch:N`:
  `parse_batch_item_dict` takes any string (`image_batch.py:376-382`), and neither builder
  (`run_one_image_prompt` `:503`, `_to_request` `:882`) reads either field. A local path is
  not even checked for existence.
- **Reach.** On flow.google.com users reach the drop through `gflow run --config`. `image
  batch` is refused there before it runs, so it reaches the drop only on an account served
  labs (not observed here; labs answers 308 on every profile we hold). Both commands are
  MCP-exempt, so there is no MCP surface.
- **The record says otherwise.** CHANGELOG (v0.52.0, #317) advertises the fields, and
  `LIVE_VERIFICATION_v0.52.0.md` row 5 records a PASS that no code at that tag could
  produce: `git grep item.ref v0.52.0 -- src` finds it only in the uncalled
  `resolve_batch_dependencies`. `tests/test_image_batch_references.py` tests only that
  uncalled function, which is why the suite stayed green.

## Not measured

The labs arm of `image batch`; whether Flow accepts a prior generation's media id as a
reference on flow.google.com (a media-UUID `--ref` is not ported there, exit 36). A local
file reference **is** ported on both hosts, and a batch downloads each row before the next,
so `batch:N` could be wired as the parent's downloaded file. **Superseded below:**
re-uploading duplicates the image in the project; the follow-up measures referencing the
generated image directly.

## Follow-up: reference row 0's generated image with no upload (owner's design)

Requirement (owner): an image the batch already generated is in the project; row N must
reference it by the handle Flow's reply returns, never by re-uploading the downloaded copy
(duplicates clutter the project). Two $0/2-image spikes, `ci-probe`, flow.google.com:

`scripts/dev/spike_mention_existing_media.py` (no submit, $0), on a project with two
same-prompt generations:

- The composer's `@` picker **does** offer generated images, under a caption Flow writes
  ("Matte grey ceramic sphere", "Ceramic sphere on white"), not the prompt. A prompt-text
  query matched nothing.
- The two same-prompt images got different captions.
- A media mention chip carries `data-reference-type="media"` and an **empty**
  `data-entity-id`; option markup carries no UUID. The DOM cannot prove which image bound.
- Mentioning an existing image made 0 requests (first pick) and 1 `as29s` (picker search);
  no upload.

`scripts/dev/spike_batch_ref_existing_media.py` (2 images), both rows through the real
`FlowApiClient.generate_image` path; row 1's `attach_references` swapped to "mention row 0
by its reply `display_name`, return row 0's media id":

| | Result |
|---|---|
| row 0 reply | `media_id` + `display_name` "Red apple on wooden table" (Flow's caption) |
| unfiltered `@` list right after row 0 | did **not** include it (same 6 older items) |
| row 1 (search by caption via `_mention_by_name`) | **completed**; production's `_image_body_problem` passed |
| row 1 `ogiZ0b` submit body | **carries row 0's media id** |
| rpcids during row 1 | 19, no `maseQ` (upload): nothing added to the project |

**Reading.** Buildable on this host today: the reply's `display_name` is the search key,
the reply's `media_id` is the identity, and the existing body check refuses the run if the
caption bound any other image (fail-safe, never silently wrong). Not measured: two images
with the same caption (the body check would refuse, not disambiguate); a row with
`count > 1` (which of its images `batch:N` means is a design decision); the labs host.
