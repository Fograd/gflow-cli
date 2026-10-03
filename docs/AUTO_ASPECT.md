# Derived Auto image aspect

`auto` derives an explicit supported ratio from the first supplied image reference.
Local PNG/JPEG references use bounded decoded bytes; existing Google UUIDs use
fresh owned native dimensions in an explicit selected project.
This is a local approximation: nearest ratio by symmetric log distance among
16:9, 9:16, 1:1, 4:3 and 3:4. It does not send a Google Auto enum or claim to
reproduce Google's or useapi's internal algorithm. Explicit ratios are unchanged.

```sh
gflow image i2i "paint this scene" --ref ./photo.png --aspect auto --json
```

Direct and queued MCP image generation use the same resolver. References retain
input order (numeric slot order for numbered references). A native first reference
never falls back to a later local file. Unavailable native dimensions, text-only
and character-only Auto refuse before generation.
Files must be bounded valid PNG/JPEG (20 MiB, 25 million pixels).

CLI JSON and MCP results retain `requestedAspectRatio`, `resolvedAspectRatio`
and `aspectPolicy` (`derived-first-reference-nearest-supported-v1`). Queued MCP
stores this decision alongside the concrete resolved ratio in the durable payload. CLI input refusals exit 2; shared service
configuration refusals use exit 11.

For `gflow run --config`, each row may set `aspect_ratio` to `auto` and `ref` to a
local file, or `batch:N` naming an earlier single-image row. Each row resolves
independently. A parent reference requires successfully downloaded local bytes.
A failed or unavailable parent download does not become a successful dependency. The resolved row outcome retains
its requested/resolved decision on `prompt.aspect_decision`. Files are uploaded
once as usual; parent images remain referenced in place. A row without a reference
refuses before its generation. `gflow image batch` remains a text-only stay-mounted
runner and directs Auto reference rows to `gflow run --config`.

Validation covers local reference resolution, input refusal, row metadata and
parent downloaded-byte resolution without browser or Google generation. The final live CLI Auto attempt failed with exit 25 (FlowAgentUiError) at shared migrated composer readiness in the current account cohort: one failed and four skipped in 54.38 seconds, with no accepted image. MCP was not given another paid attempt after the shared underlying blocker. This historical generation failure does not establish native-ID sizing failure.
Accepted CLI/MCP Auto generation remains unverified. Google native Auto remains unsupported; this local policy is not a Google Auto sentinel.

## Existing Google image UUIDs

CLI I2I and direct/queued MCP also resolve Auto from the **first supplied Google
image UUID**, when an explicit existing project is selected. The SDK method is
`await client.resolve_native_image_aspect(project_id, media_id)`. One fresh native
project read must prove a unique active typed image and positive bounded width
and height. Missing dimensions, wrong kind, archived assets and ambiguous
workflows fail before generation. No CDN request or caption guess supplies a ratio.
The same nearest-supported approximation and requested/resolved/policy result
metadata apply; this remains a local policy rather than a Google Auto enum.

Managed HTTP references continue to use their bounded decoded local bytes.
Arbitrary unregistered Google IDs remain outside the HTTP asset-registry contract;
this change does not invent a registry mapping. Batch parent references require
actual downloaded bytes. Failed or unavailable parent downloads remain refused.
Read-only native-ID sizing BDD passed on 2026-10-03: one actual owned image
reported1024×1024 and resolved1:1 in7.68seconds. No generation/upload occurred.
This proves fresh metadata sizing for that profile, not accepted Auto generation.
