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

Optional repeated `--image-ref` accepts up to five active same-project image
UUIDs; `--audio-ref` accepts up to three active owned native audio media UUIDs.
Saved TTS visibility is not required. `--character-ref` accepts up to seven
active owned character entity UUIDs. These are outer bounds: fresh native model
capacities also constrain the combined image, character and audio reference pools.
Character weights use their proven active entity-owned image/audio links;
missing or ambiguous ownership or model limits fails before token minting.

The shared structured prompt codec preserves canonical markers such as
`@referenceImage_3`, `@referenceAudio_1` and `@character_2`. CLI/MCP references
use ordered lists. SDK `reference_slot_ids` and REST positional fields preserve
holes and mixed image/character UUIDs in `referenceImage_N`; fresh classification
retains the original marker. SDK `character_ids`, direct MCP `character_ref`,
and REST `character_1..7` mirror the CLI. The durable REST worker forwards
`characterMediaIds` and `referenceSlotIds`; no queued MCP edit twin is claimed.
Available system presets are also audio inputs: use a known name such as `Charon` or the exact native resource `voices/charon`. Both normalize to one identity; equivalent-form duplicates refuse. Fresh native system-catalog availability is required before minting; bundled recognition alone is insufficient. UUIDs retain strict active owned audio validation. Explicit presets consume the native audio pool, including refusal at zero/unknown capacity. Arbitrary URLs/resource prefixes are not accepted.

The SDK helper is `api.native_video_edit.edit_native_video(client, ...)`, followed
by `wait_native_video_edit(client, started)`. The same checked-out project page
mints VIDEO_GENERATION. Preassigned output IDs are derived from invocation-owned
seeds using the shared native UUID assignment function. CLI checkpoints the
identities in a mode600 `edit-started.json` before a single dispatch. Unknown
acknowledgement/poll outcomes return a typed nonretryable error; inspect those
IDs before any manual resubmission. Cancellation propagates to the caller.

The codec places source media/start/end in request field1, structured prompt in
field2, model in field3, aspect in field4, output-seed metadata in field5, image
refs in field9, audio refs in field10 and characters in field11. This differs from extension metadata
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

### Character preflight evidence
The free synthetic video/character BDD passed one test with two warnings in
55.13 seconds. It exercised the actual SDK mixed referenceImage_3 character
path, fresh active source/entity ownership and native model capacities, then
stopped before token minting. Zero generation requests were sent; only its
character/video fixtures were removed and original active media remained.
Run tests/e2e/test_native_edit_characters_bdd.py with explicit private
GFLOW_CLI_E2E_PROFILE/HOME/RESOURCES_PROJECT and GFLOW_CLI_E2E_EDIT_CHARACTERS=1.
This proves live preflight, not accepted edited video or semantic grounding.

### System-preset preflight evidence

The free synthetic-video preset preflight BDD passed1test,2warnings in45.63seconds.
Both actual SDK R2V and V2V positional referenceAudio_3 preset paths reached
their token boundaries; no token was minted and zero generation requests were
sent. Only the synthetic upload was archived; original active media remained.
Run tests/e2e/test_native_preset_audio_bdd.py with explicit private
GFLOW_CLI_E2E_PROFILE/HOME/RESOURCES_PROJECT and GFLOW_CLI_E2E_PRESET_AUDIO=1.
Native catalog presentation uses capitalized names; normalized uniqueness is
case-insensitive, while the wire resource is lowercase.
This proves live preflight, not accepted rendered video or speech.

## R04 supported reference inputs and implementation closure

R2V and V2V use the same strict native audio ownership check: an exclusive nonempty
native audio arm, exact selected project/media/workflow identities and one active
owned workflow. Saved-TTS visibility is not required. An uploaded generic audio
asset remains generic audio; it is not automatically a saved voice or eligible for
saved-voice aliases. Local audio paths, arbitrary URLs and unknown resource forms
refuse. This work accepts existing native audio; it does not add audio ingestion.
R2V permits at most five explicit audio refs; editing permits three. Fresh account
model limits can lower these bounds. Model reads now return max_images, max_audio
and max_characters; unknown or duplicate capacities refuse generation preflight.
Character-linked image/audio weights keep the measured native pool policy.

CLI `--reference-slot SLOT=REFERENCE` is repeatable on `reference-native` and
`edit-native`. Direct MCP uses `reference_slot_ids`, a JSON object. Explicit maps
replace image/audio/character lists on those adapters. SDK `reference_slot_ids`
and REST positional fields retain their existing contracts. Fresh classification
can bind a character under `referenceImage_3` without renumbering it to
`character_1`; prompt occurrences retain their original order, including repeats.

~~~bash
gflow video reference-native --profile PROFILE --project PROJECT_UUID \
  --prompt "Use @referenceImage_3 beside @referenceImage_1 with @referenceAudio_3" \
  --reference-slot "referenceImage_1=IMAGE_UUID" \
  --reference-slot "referenceImage_3=CHARACTER_UUID" \
  --reference-slot "referenceAudio_3=AUDIO_UUID" --json
~~~

These are generation examples, not zero-cost verification commands. For editing,
use `video edit-native VIDEO_UUID` with the same slots, a freshly returned
`--model-key` and an eligible active source. Missing video dimensions or an aspect
outside the exact supported 16:9, 9:16 or square ratios fails clearly before mint.

The 5 October zero-generation existing-audio BDD passed in 42.04 seconds. It
resolved the operator's saved voice and fresh models, built both actual final
codecs at the pre-mint boundary and verified repeated audio slot three. No token,
output checkpoint or submission occurred. Only its labelled synthetic source clip
was archived; original media remained active. Earlier character and system-preset
preflight evidence above is reused. Twelve current strict catalogs exposed no
unsaved uploaded-audio cohort; a known empty catalog refused strict ownership
reading. Controlled tests cover supported unsaved native audio, five-versus-three
bounds, malformed/archived/foreign links, ordering, missing slots and account
separation. Live upload-origin shape coverage remains an evidence limitation.
Rendered output, audible speech and semantic influence belong to R12.

Rerunnable BDD: `tests/e2e/test_native_reference_audio_bdd.py -m e2e_auth` requires
private `GFLOW_CLI_E2E_PROFILE/HOME/RESOURCES_PROJECT`, existing native audio UUID
in `GFLOW_CLI_E2E_REFERENCE_AUDIO`, and `GFLOW_CLI_E2E_REFERENCE_AUDIO_PREFLIGHT=1`.
Prefer an eligible source in `GFLOW_CLI_E2E_REFERENCE_AUDIO_VIDEO`. When none exists,
explicit `GFLOW_CLI_E2E_REFERENCE_AUDIO_SOURCE_FIXTURE=1` permits one labelled free
synthetic MP4 upload and archive. Do not replay an uncertain upload/archive. This
BDD cannot establish upload-origin audio if the supplied asset is a saved voice.
