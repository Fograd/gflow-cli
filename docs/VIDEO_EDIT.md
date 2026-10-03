# Native Omni video editing

The draft SDK and `gflow video edit-native` expose a dedicated source-derived
Omni edit operation, separate from extension or local concatenation. The codec
comes from the deployed Google Angular E4a/I4a `jIps6` builder. Live paid output
acceptance is deferred to the final E2E phase.

```sh
gflow video edit-native MEDIA_UUID --project PROJECT_UUID \
  --prompt "change the background" --model-key ACCOUNT_NATIVE_EDIT_KEY \
  --start-frame 0 --end-frame 120 --out-dir ./out/edits --json
```

Run `gflow video edit-models --project PROJECT_UUID` to read actual edit-capable
keys and account-tier credit metadata. Use one returned native key for the account. The source must be
an active typed video in the selected project. Output count is one and aspect
inherits measured source dimensions. An explicit end frame is required until a
source duration decoder is established; the fork does not guess the clip end.
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
