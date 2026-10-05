# Native standalone video extension

The implementation uses the deployed native Flow Angular
`VideoFxService.BatchAsyncGenerateVideoExtendVideo` (`fZytfe`) request,
rather than the older labs scene extension and concatenation path. **Google
acceptance and final downloaded-video verification are pending the final E2E pass.**

## CLI and SDK

```sh
gflow video extension-models --project PROJECT_UUID --profile pro1 --json
gflow video extend-native SOURCE_MEDIA_UUID --project PROJECT_UUID \
  --prompt "Continue the camera movement" --profile pro1 --count 1 --json
```

The default reads native GetModels and account tier, then selects the lowest-cost
available extension usage matching the source aspect. `--model-key` selects an
exact discovered native key. This interface does not guess keys from public Veo
model aliases. Count is 1–4. Aspect defaults to the source dimensions; an explicit
aspect must match. Optional `--trim-start-frame` and `--trim-end-frame` encode
the deployed source-video frame fields; no fixed FPS or whole-clip length is
assumed. A public numerical generation seed is not implemented by this adapter.

SDK methods:
`await client.list_native_extension_models(project_id)`,
`await client.extend_native_video(...)`, and
`await client.wait_native_extension(started, timeout_s=600)`.
Submission returns the project/source media plus output media and workflow IDs.
The result is the independently identified extension output, without automatic
scene concatenation.

## Private HTTP operation worker

```sh
python -m gflow_cli.selfhost.extension_worker PROFILE PROJECT_UUID REQUEST_JSON_PATH
```

The private JSON accepts `mediaGenerationId`, `prompt`, optional HTTP `model`
(defaultFast inserted by REST) or exclusive `modelKey`,
`count`, `aspectRatio`, `trimStartFrame`, `trimEndFrame`, and `timeout`.
Output is `video_extension_result` with `project_id`, `source_media_id`,
and `results` containing `media_name`, `media_id`, `workflow_id`, and
`local_path`. Files are written beside the private request JSON. Root's REST
adapter supplies ownership, authentication, queue and response modes.

Before dispatch, `extension-started.json` records the actual derived output
identifiers. The frontend sends UUID seeds in metadata; its SHA-256 UUID
derivation is reproduced to obtain the output IDs before dispatch. Those internal
seeds are excluded from public errors and DTO representations.

No generation is automatically retried. An ambiguous dispatch or result identity
returns a safe `NativeExtensionUnknownError` envelope and worker exit 40 with
known output IDs. Polling reads only those IDs and crosschecks project/workflow;
it never adopts the first new library tile. HTTP consumers must inspect or poll
the known job rather than resubmit after uncertainty.

## Primary source evidence

The official deployed Angular project bundle SHA-256 is
`fde0520503cde337170e1314e9904b1da4e279d0fea2f10df7cb417ac448d31b`.
The codec follows K4a/O4a/P4a and t7a; standalone mode follows WXa/VXa.
Output assignment follows yQ/pVa and h8a. Model metadata follows
HTrJv/GetModels, U6a/R6a, and tier data from nzlxg/GetCredits.

Focused offline tests verify positional encoding, exact output assignment,
validation before checkout, current-tier model filtering, one dispatch after
checkpoint, exact-ID result correlation and CLI registration. These tests do not
establish generation acceptance.


## R11 HTTP model contract

POST /videos/extend defaults to model=veo-3.1-fast, rather than choosing the
cheapest extension family. Explicit model supports the four Veo aliases including
lite-low-priority; fresh tier/aspect metadata must contain the exact family.
Missing families refuse before token mint; no key is guessed. Alternatively
supply modelKey, with model omitted. HTTP landscape/portrait aliases normalize
to16:9/9:16. Explicit invalid modelKey/aspect/project controls refuse; omitted
aspect is inherited. JSON and text multipart trimStartFrame/trimEndFrame reach
the existing integer frame codec.

The shared SDK accepts an optional canonical model_family selection filter used
by the private HTTP worker. Existing native SDK/CLI/direct MCP calls with neither
filter nor model_key keep the cheapest available compatible selection. The
existing exact-key controls and source/project checks are retained. R11 verifies
selection and dispatch with controlled outcomes and current pro2 read-only model
metadata; accepted extension rendering still requires separate R12 permission.
