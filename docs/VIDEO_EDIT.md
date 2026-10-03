# Native Omni video editing

The draft SDK and `gflow video edit-native` expose a dedicated source-derived
Omni edit operation, separate from extension or local concatenation. The codec
comes from the deployed Google Angular E4a/I4a `jIps6` builder. Live paid output
acceptance is deferred to the final E2E phase.

```sh
gflow video edit-native MEDIA_UUID --project PROJECT_UUID \
  --prompt "change the background" --model-key ACCOUNT_NATIVE_EDIT_KEY \
  --start-frame 0 --out-dir ./out/edits --json
```

Run `gflow video edit-models --project PROJECT_UUID` to read actual edit-capable
keys and account-tier credit metadata. Use one returned native key for the account. The source must be
an active typed video in the selected project. Output count is one and aspect
inherits measured source dimensions. Omit CLI --end-frame, MCP end_frame or
HTTP endFrameIndex_1 to resolve min(floor(sourceDurationSeconds*24),240).
Missing/invalid duration or an end at/before start fails before mint/submission.
An explicit end remains unchanged and does not require duration metadata.
Frames are the useapi virtual24fps window: start0–239/end1–240, end greater than
start. `duration` and start/end images are not edit inputs.

Optional repeated `--image-ref` accepts up to five active same-project existing
image UUIDs; `--audio-ref` accepts up to three same-project saved voice UUIDs.
System preset names, character refs and inline positional markers are not yet
accepted by this dedicated form. The encoder uses source-proven image field9
and audio field10. No local upload or unverified reference substitution occurs.

The SDK helper is `api.native_video_edit.edit_native_video(client, ...)`, followed
by `wait_native_video_edit(client, started)`. The same checked-out project page
mints VIDEO_GENERATION. Preassigned output IDs are derived from invocation-owned
seeds using the shared native UUID assignment function. CLI checkpoints the
identities in a mode600 `edit-started.json` before a single dispatch. Unknown
acknowledgement/poll outcomes return a typed nonretryable error; inspect those
IDs before any manual resubmission. Cancellation propagates to the caller.

The codec places source media/start/end in request field1, structured prompt in
field2, model in field3, aspect in field4, output-seed metadata in field5, image
refs in field9 and audio refs in field10. This differs from extension metadata
field6. Focused tests prove encoding, active ownership refusal before token mint,
checkpointing/one dispatch/correlated acknowledgement, and CLI argument refusal.
No generated video or rendered speech is claimed by those tests.


### Source duration and verification

The default reads the deployed frontend's actual video metadata: video field2 LI, field3 qx Duration, seconds plus nanoseconds / 1e9. Asset row coordinate: [7][1][2]. No model duration or frontend fallback is used. Source still passes fresh active ownership/type validation before resolving the window. Virtual24fps is independent of encoded frame rate.

SDK returns NativeVideoEditStarted with start_frame, end_frame and optional source_duration_seconds. CLI, MCP and HTTP results expose startFrameIndex, endFrameIndex, and sourceDurationSeconds when measured. Explicit-end requests do not need duration metadata.

A read-only original-profile probe on 2026-10-03 observed an owned one-second video and resolved end24, with zero generation, download or solver calls. This proves metadata decoding and window resolution; accepted edited-video rendering is separate.

Rerunnable read-only BDD: set GFLOW_CLI_E2E_NATIVE_VIDEO_PATH=duration-metadata plus private GFLOW_CLI_E2E_PROFILE, GFLOW_CLI_E2E_HOME and GFLOW_CLI_E2E_RESOURCES_PROJECT, then run tests/e2e/test_native_video_duration_bdd.py with repository authentication gates. It reads one project snapshot and never calls generation.

The actual read-only duration BDD passed1test with2warnings in8.22seconds.
No video generation or solver task was submitted.
