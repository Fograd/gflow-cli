# Native standalone video extension

The implementation uses the deployed native Flow Angular
`VideoFxService.BatchAsyncGenerateVideoExtendVideo` (`fZytfe`) request,
rather than the older labs scene extension and concatenation path. **Accepted standalone extension remains unproved: R12 Google submission was
explicitly refused.** Free recovery of a retained generic clip is validated; it
does not prove a newly rendered extension.

## CLI and SDK

```sh
gflow video extension-models --project PROJECT_UUID --profile pro2 --json
gflow video extend-native SOURCE_MEDIA_UUID --project PROJECT_UUID \
  --prompt "Continue the camera movement" --profile pro2 --count 1 --json
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


R12 measured source compatibility: when Google explicitly omits both video
dimensions, edit/extension preflight reuses the strict active owned-video lookup
and bounded MP4 measurement already used by native promotion. Unknown ownership,
malformed dimensions and unsupported aspect still refuse before solving/dispatch.
See [actual campaign evidence](FINAL_E2E.md#r12-measured-campaign--5-october-2026).


## Validated output recovery

CLI/REST worker and direct MCP extension outputs share exact checkpoint-bound
download validation. Every result must match the reserved ordered media/project/
workflow list and fresh owned video metadata before download. Fresh protected
URLs use the existing unauthenticated bounded downloader: no redirects or
browser cookies, actual MP4/dimension checks, exclusive writes. Existing output
files are never overwritten. Use a new recovery directory when validated siblings
already exist; preserve those siblings and the original checkpoint. A missing,
invalid or failed download returns nonretryable uncertainty with the original
handles; cancellation propagates and temporary bytes are removed. Neither path
replays submission to recover a download.

The PR882 comparison and zero-generation retained-clip proof are documented in
[FINAL_E2E](FINAL_E2E.md#pr882-focused-comparison-and-recovery-repair--7-october-2026).
Its scene extension schema is separate from this standalone adapter.


## R13 free diagnosis — 11 October 2026

No demonstrated same-operation request defect was found, so no runtime or DTO
change was made. The retained R12 V5r standalone extension remains explicitly
refused (`fZytfe`, `PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC`, gRPC8).
A fresh read of its exact reserved output returned gRPC5 NOT_FOUND; its source
still passed fresh selected-project/media/workflow ownership checks.

The comparison used V5r's original owning pro2 profile and source. Original pro3
also passed the required fresh identity, credit and extension-model preflight.
Both reported1050 credits; final guarded before/after balances were unchanged.
The exact Lite extension key remains listed alongside Fast/Quality alternatives.
These reads do not establish generation acceptance or renew campaign allowances.

**No matching standalone UI capture.** The current project displayed the Agent
composer. The source menu exposed Add to scene and Add to prompt. Switching mode
attempted `DA4VGb` UpdateUserSettings and `Kcr7Ub` UpdateAgentInfo; the guard aborted
both, including the UI's repeated attempts. No scene, project, upload, character,
voice, generation, preview or solver task was created. Media-load errors under
this restricted guard are not evidence of unavailable standalone extension.

Current official bundle SHA256
`7747d72648a64754698d09a92a905162b0e165795cd0a4211f7be6b59f6073ab`
still contains the standalone `EXTEND_VIDEO` branch on `fZytfe`. Source/prompt/
model/aspect/metadata remain at request fields1/2/3/4/6; source media and optional
trims remain at source-video fields2/3/4. Tool22, `VIDEO_GENERATION`, project
context field6 and token field11 are still visible. Additional setters at fields
8–13 include optional references and non-default resolution. Their presence does
not prove that matching standalone input must populate them, or that their absence
caused V5r. This is lower-confidence static evidence, not an actual UI submission.

V5r retained caller arguments, refusal and output checkpoint, not a complete raw
historical request with headers/token/assignment seeds. Exact wire equivalence,
current standalone acknowledgement/output correlation and token quality remain
unmeasured. PR882's scene context/workflow/frame window is still not a justified
replacement for this standalone DTO.

The diagnostic guard used a closed invocation-local proxy during profile launch,
then installed browser-context HTTP/WebSocket interception with service workers
blocked before opening the proxy and allowing bootstrap. Three browser canaries
per invocation blocked an extension RPC, a mixed read/write batch and an unknown
GET before navigation. Only positively identified reads were forwarded; uploads,
resource writes, unknown requests and solver hosts were denied. Eight retained
invocations passed24 canary checks; two initial harness limitations were recorded.
Forwarded provider mutations, generation submissions and solver tasks were all0.
No cookie copying/import, profile replacement, registration changes or deliberate
sign-out occurred. This does not claim authentication renewal.

R12 ledger and historical budget hashes/counters remained unchanged, including
both exhausted video allowances. No acceptance checkbox was promoted. First
obtain a matching standalone blocked capture; changing the current Agent mode
would require separately authorised writes. No paid retest is justified until a
concrete difference is demonstrated. A later test would need a new explicit
count-one video allowance and a separate solver allowance if applicable, with
no automatic retry. See [R13 verification](FINAL_E2E.md#r13-free-refusal-diagnosis--11-october-2026)
and the operator's R13_HANDOFF.md for private evidence and exact publication state.
