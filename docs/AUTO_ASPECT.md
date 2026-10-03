# Local Auto image aspect

`auto` derives an explicit supported ratio from the first local PNG/JPEG reference.
This is a local approximation: nearest ratio by symmetric log distance among
16:9, 9:16, 1:1, 4:3 and 3:4. It does not send a Google Auto enum or claim to
reproduce Google's or useapi's internal algorithm. Explicit ratios are unchanged.

```sh
gflow image i2i "paint this scene" --ref ./photo.png --aspect auto --json
```

Direct and queued MCP image generation use the same resolver. References retain
input order (numeric slot order for numbered references). A UUID as the first
reference refuses even if a later local file is available; native IDs do not
provide decoded dimensions. Text-only and character-only Auto also refuse.
Files must be bounded valid PNG/JPEG (20 MiB, 25 million pixels).

CLI JSON and MCP results retain `requestedAspectRatio`, `resolvedAspectRatio`
and `aspectPolicy` (`derived-first-reference-nearest-supported-v1`). Queued MCP
stores this decision alongside the concrete resolved ratio in the durable payload. CLI input refusals exit 2; shared service
configuration refusals use exit 11.

For `gflow run --config`, each row may set `aspect_ratio` to `auto` and `ref` to a
local file, or `batch:N` naming an earlier single-image row. Each row resolves
independently. A parent reference requires successfully downloaded local bytes;
an undownloaded native result is insufficient. The resolved row outcome retains
its requested/resolved decision on `prompt.aspect_decision`. Files are uploaded
once as usual; parent images remain referenced in place. A row without a reference
refuses before its generation. `gflow image batch` remains a text-only stay-mounted
runner and directs Auto reference rows to `gflow run --config`.

Validation covers local reference resolution, input refusal, row metadata and
parent downloaded-byte resolution without browser or Google generation. The final live CLI Auto attempt failed with exit 25 (FlowAgentUiError) at shared migrated composer readiness in the current account cohort: one failed and four skipped in 54.38 seconds, with no accepted image. MCP was not given another paid attempt after the shared underlying blocker. CLI/MCP Auto has offline coverage only. Google native Auto remains unsupported; this local policy is not a Google Auto sentinel.
