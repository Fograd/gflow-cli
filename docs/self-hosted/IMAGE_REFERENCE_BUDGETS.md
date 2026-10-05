# Fresh native image reference budgets

R08 supported implementation is complete. References use current model metadata
and fresh active ownership before local upload, token mint or submission. The
existing composer and validators are shared; native Google Auto is not claimed.

## Supported forms and order

Python accepts ordered `ImageRef` native UUIDs, local PNG/JPEG `ref_paths` and
owned character entity IDs. CLI uses repeated `--ref` and `--reference-entity`;
MCP uses `reference_images` and `reference_entities`. For mixed local/native
inputs use CLI `--reference-syntax slots` or MCP `reference_syntax="slots"`.
`@reference_N` follows the caller's image input order; `@character_N` follows
character input order. Repeated prompt markers retain their positions but attach
one identity. Names mode keeps existing saved-name resolution; ambiguous names
refuse. Mixed names-mode inputs requiring an ordered plan remain guarded.

REST `POST /images` uses `reference_1` through `reference_10` and `character_1`
through `character_7`, with numeric slot order preserved, including holes.
Image slots accept managed decoded image asset IDs, owned native image UUIDs and
exact registered image aliases; character slots accept owned entity UUIDs and
exact registered character aliases. Aliases must be explicit verified mappings
for the selected account/project, never arbitrary vendor identifier decoding.
REST accepts managed assets rather than caller filesystem paths. Unregistered
native UUIDs require an explicit enabled account and selected/default project.
Missing, inactive, foreign, malformed or ambiguous references refuse.

## Fresh independent limits

```sh
gflow image reference-models --project PROJECT_UUID --profile pro2 --json
```

Python: `FlowApiClient.list_native_image_reference_models(project_id)`.
MCP: `gflow_list_image_reference_models(project, profile)`.
REST: `GET /v1/google-flow/images/reference/models?email=ACCOUNT_HANDLE&projectId=PROJECT_UUID`.
These are read-only. Use original pro2/pro3; pro1 is disabled and reserved.

Each row reports `model_key`, `advertised_reference_cap`,
`transport_reference_cap`, `effective_reference_cap`,
`advertised_character_cap` and `effective_character_cap`.
Image capacity is the smaller of the advertised capacity and transport ceiling
(ten for Nano Banana 2/Pro/Lite). Character capacity is separately capped at seven;
advertised zero disallows characters. Every actual owned character image also
consumes the image pool. Eight standalone images plus a two-image character use
ten image slots and one character slot. Each separately uploaded local path
counts; supplied character weights are replaced with fresh actual weights.
Eleven inputs, smaller observed budgets or too many characters refuse before
upload or mint. Missing, duplicate, off-tier, disabled or malformed models refuse;
no subscription name grants a capacity. Imagen 4 remains unsupported on the
current native composer, even though its legacy DTO ceiling is three.

Fresh 5 October pro2/pro3 REST and MCP observations exposed Nano2/Pro/Lite,
each with ten effective image slots and seven effective character slots.
Catalog `retained_reference_verified=false` and `rendering_verified=false` describe
the catalog observation; they do not erase historical accepted evidence.

## Existing controls and Auto

Only existing model aliases, count integers 1–4, seed integers
`0..2147483647-count+1`, and ratios `1:1`, `9:16`, `16:9`, `4:3`, `3:4`
are supported. SDK DTOs require model/aspect enums; CLI/queue adapters translate
supported strings. Explicit empty/unsupported choices, boolean/fractional counts
and invalid seeds refuse rather than silently selecting defaults. Native seeded
outputs use seed+index and verify returned seeds; this does not promise identical
pixels. Unsupported host/transport seed paths refuse before submission.

The existing Auto approximation uses the first ordered image reference, not the
first prompt mention or first available later image. Local images use bounded
decoded dimensions; native IDs use fresh owned dimensions. Character-only,
text-only or dimensionless-first Auto refuses. Explicit ratios are forwarded
unchanged. Results preserve requested/resolved aspect and policy metadata.
This nearest-supported-ratio policy is distinct from Google's native Auto control.
Defaults remain interface/model specific; see [Auto aspect](../AUTO_ASPECT.md).

## Acceptance evidence and remaining R12

The accepted 4 October original-pro2 `HARBOR_SEAL` (Lite), count-one SDK/canonical
slot campaign ran on source baseline
`890a65918255d5a71065a82af0e0bd61a404c2b0` plus the composer corrections
committed as `a7846083edfeb61861bb8c5f8cf23d2af3215cb7`.
The retained corrected follow-up records ten exact ordered native identities,
canonical positional wire validation, one captured request, one source dispatch,
one fresh owned accepted JPEG decoded at 768×1376, and whole-composer clear10→0.
Invocation-owned fixtures were archived; originals were preserved.
A separate earlier accepted output was recovered read-only after a PNG/JPEG path
mismatch; it was not replayed. See [the ledger](VERIFICATION.md#composer-and-video-upload-corrections--4-october).

This establishes ordered attachment/request preparation and accepted ten-reference
Lite output, not the independent visual influence of every reference, every model,
or ten-reference rendering through each public wrapper. That rendered acceptance
stays separately under R12 and requires a new explicit allowance. R08 uses fresh
zero-generation original-library preflights and controlled interface/worker tests;
no generation, audio preview, upscale or paid solver request is part of its closure.
