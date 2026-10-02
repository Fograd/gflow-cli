# Native portrait and body image references

## Question and pre-registered reading

Does the second existing-image reference append a body reference while preserving
the portrait and both source images? Two distinct authoritative refs means append;
first ref missing means replacement (do not report success); selector misses are
inconclusive. Generation submits are blocked throughout this metadata-only probe.

## Measured UI and wire

The existing character editor's `flow-slot-chip-button` with the
`accessibility_new` icon switches to the empty body slot. Its
`flow-character-image-preview` component exposes an upload button and an `add`
button opening the project image picker. Selecting an owned existing image caused
`Sc7aEb`, the same native copy RPC as the portrait, with
`args[7][2][1] = [1]`; the portrait uses `[0]`. This is an indexed portrait/body
contract, not arbitrary reference count support.

The acknowledgement included a new media and workflow whose project/entity IDs
matched the owned character. An authoritative `Zzl0ze` character read retained both
copied workflows. The original portrait source and body source remained active.
After deleting only the owned test character, both originals still remained active
and the test character was absent. No generation or solver task was submitted.

The driver now atomically validates the entire reference set against active native
project ownership before creating an entity. Measured `batch_media_ids` membership
also resolves a nonrepresentative generated-image output to its owning workflow.
Both copy requests, visibility reads and optional initial personality update share
the existing 45-second post-create deadline. Success requires every acknowledged
copied workflow to remain visible; replacement or partial failure preserves the
created character reference/project for inspection and never retries a mutation.
REST additionally verifies both managed files decode as PNG/JPEG and belong to the
same account/project before invoking the private worker.

## Verification

The new browser-bound metadata BDD passed **1 in 34.11 seconds**. It used two owned
existing images, asserted two distinct copied workflows disjoint from both original
workflows, read both references from the native catalog, deleted the owned test
entity and verified both originals were active. The earlier exploratory probe was
also cleaned up. Offline tests cover atomic unowned-second refusal, owned batch
membership, second-copy partial failure, replacement refusal and worker argument
preservation. Full HTTP proof is recorded separately in self-hosted verification.

Run the opt-in BDD with existing authenticated profile/home/project inputs plus
`GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA` and
`GFLOW_CLI_E2E_CHARACTER_SECOND_MEDIA`, both already verified owned image IDs:

```sh
pytest tests/e2e/test_selfhost_character_second_reference_bdd.py -m e2e_data --no-cov
```

This establishes portrait/body binding only. It does not measure custom saved voice
CRUD, voice assignment/rendered audio, arbitrary third references or generated
portrait/body creation. Private captures remain gitignored; public evidence omits
account/project/media identities and signed URLs.
