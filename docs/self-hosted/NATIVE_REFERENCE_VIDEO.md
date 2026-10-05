# Native video with image, audio and character ingredients

The native reference-video adapter encodes Flow's deployed Q4a/MZZa6b request. SDK, CLI and worker implementation is tested offline. **Google generation acceptance remains pending final E2E.** Existing image/audio UUID ingredients must belong to the selected project and appear with the correct exclusive native media type in a fresh snapshot.

Select an enabled original profile (pro2 or pro3 in this deployment); pro1 remains disabled and reserved for UseAPI. Discover current account-tier model keys:

```sh
gflow video reference-models --project PROJECT_UUID --with-audio --profile PROFILE --json
```

Generate from ingredients, using a discovered key:

```sh
gflow video reference-native --project PROJECT_UUID --profile PROFILE \
  --image-ref IMAGE_UUID --audio-ref AUDIO_UUID \
  --model-key DISCOVERED_KEY --prompt 'Animate @referenceImage_1 to @referenceAudio_1' \
  --aspect 16:9 --resolution 720p --count 1 --json
```

The absolute local budgets are zero to seven images and zero to five audio ingredients and zero to seven characters, with at least one ingredient. Each model's fresh capabilities can lower those budgets. Audio-only requests are encoded with an empty image vector. `@referenceImage_N` and `@referenceAudio_N` preserve their position as typed native prompt chunks. Unknown marker families remain literal. Missing reserved slots fail before submission. Ingredients not mentioned in the text still appear in the explicit attachment vectors.

Omitting `--model-key` searches only a current tier-available family whose native display name contains Omni and Flash. If no matching family exists, discover and supply an exact key; another video family is never silently chosen for that default. `--duration` selects a usage with that exact advertised duration; it does not inject a guessed numeric duration field. Resolution uses the deployed enum (720p default, 360p/1080p/4K only when advertised by the selected usage). Supported native video aspect enums are 16:9, 9:16 and square.

The SDK exposes `generate_native_reference_video`, `wait_native_reference_video` and `list_native_reference_video_models`. Generation returns paired assigned media/workflow UUIDs, invokes `on_started` before dispatch, and submits once. `NativeVideoGenerationUnknownError` uses exit40 with bounded safe output handles and phase; inspect those handles before resubmitting. Assignment UUID seeds are private correlation inputs, unrelated to numerical generation seed.

The private worker is `python -m gflow_cli.selfhost.reference_video_worker PROFILE PROJECT_UUID REQUEST_JSON_PATH`. Request keys are `prompt`, `referenceImageIds`, `referenceAudioIds`, `referenceCharacterIds`, optional `referenceSlotIds` preserving canonical indices, optional `modelKey`, `count`, `aspectRatio`, `duration`, `resolution` and `timeout`. Successful output contains `type: video_reference_result`, `project_id`, and `results` with `media_id`, `media_name`, `workflow_id`, `local_path`. Parent-owned authenticated HTTP/MCP integration is documented in its corresponding API guide when finalized.

Numerical seeds for normal native video generation have not been located in the inspected deployed text/frame/reference/extension builders. A proven numerical upsample seed setter does not establish generation seed support. The adapter does not guess a skipped protobuf field.

## Prepared final video E2E batch

`tests/e2e/test_native_video_paths_final_bdd.py` binds one count-one scenario for extension, edit and reference video, plus a free reference-model/credits scenario. Preparation has been verified with billing gates unset: four scenarios skip and the BDD binding guard passes. **This is not a live acceptance result.**

Private common environment is `GFLOW_CLI_E2E_PROFILE`, `GFLOW_CLI_E2E_HOME`, `GFLOW_CLI_E2E_RESOURCES_PROJECT` and `GFLOW_CLI_E2E_NATIVE_VIDEO_OUTPUT` (a persistent private directory). Set `GFLOW_CLI_E2E_NATIVE_VIDEO_PATH=catalogs` and run `pytest tests/e2e/test_native_video_paths_final_bdd.py -m e2e_auth` for model/credit reads only.

For a single paid scenario, additionally set `GFLOW_CLI_E2E_RUN_VIDEO=1`, `GFLOW_CLI_E2E_NATIVE_VIDEO_BUDGET=1`, and select exactly one `GFLOW_CLI_E2E_NATIVE_VIDEO_PATH=extension|edit|reference`. Run the file with `-m e2e_video`. Extension/edit require `GFLOW_CLI_E2E_NATIVE_VIDEO_SOURCE` with an existing owned eligible source UUID. Edit also requires explicit `GFLOW_CLI_E2E_NATIVE_VIDEO_END_FRAME` in 1–240, derived from the known clip rather than guessed. Reference inputs are JSON UUID arrays in `GFLOW_CLI_E2E_NATIVE_VIDEO_IMAGES` and `GFLOW_CLI_E2E_NATIVE_VIDEO_AUDIO`; either or both may be supplied, with at least one ingredient.

Optional `GFLOW_CLI_E2E_NATIVE_VIDEO_MODEL_KEY` must appear in the freshly read corresponding catalog. Otherwise the scenario selects the lowest-credit suitable observed key. Reference selection intersects ingredient budgets and landscape capability; all requests use count one and the native 720p default. `ffprobe` must be installed before the billing allowance is consumed. The scenario checks exact assigned project/media/workflow correlation, downloads one output and checks decoded video dimensions.

The selected mode's output subdirectory contains a mode600 exclusive `allowance` and `checkpoint.json`. Reusing it raises instead of replaying, regardless of success, timeout or uncertain outcome. Preserve it and inspect the checkpoint before an operator explicitly grants a new allowance directory. No automatic archive/delete/restore, fallback generation or provider solve occurs in these scenarios. Run each paid mode separately under the final coordinated browser lease.

### Combined audio-reference acceptance

Select `GFLOW_CLI_E2E_NATIVE_VIDEO_PATH=audio-reference` to reuse **one** TTS preview for saved-voice CRUD, owned-character voice binding and audio-reference video generation. This additionally requires `GFLOW_CLI_E2E_RUN_TTS=1`, `GFLOW_CLI_E2E_TTS_BUDGET=1`, and `GFLOW_CLI_E2E_CHARACTER_FIRST_MEDIA` containing an existing privately catalogued image UUID. The usual video opt-in and count-one budget are also required. Do not separately run the TTS lifecycle scenario when using this combined allowance.

The scenario creates one saved voice, reads its acknowledged audio media identity, creates an owned test character from the existing image, verifies the saved voice binding, and submits one native reference video using that image and audio. After successful download/ffprobe only, it deletes exactly the acknowledged test character and voice, verifies original voice/media identities remain, and leaves the video output available for inspection. Any uncertain creation, generation or download failure leaves the private checkpoint and performs no cleanup or retry. Preparation checks are offline only: five gated scenarios skip safely and five binding checks pass; actual acceptance remains pending.

## Final acceptance status

Native credit and model/catalog reads passed live. One count-one reference-video attempt using the native browser token reached Google and received explicit PUBLIC_ERROR_UNUSUAL_ACTIVITY rejection. No accepted video is claimed. A controlled CapSolver Enterprise v3 proxyless VIDEO_GENERATION trial completed: one solved token, one submission, zero accepted outputs and one PUBLIC_ERROR_UNUSUAL_ACTIVITY rejection (gRPC 7). It made no retry. Do not retry a submitted request automatically or treat catalog availability as rendered output proof.

### R04 native character reference video
SDK reference_character_ids, CLI video reference-native --character-ref and
registered MCP gflow_generate_native_reference_video character_ref accept owned
character UUIDs. REST POST /videos with model=omni-flash accepts character_N,
or mixed image/character UUIDs in referenceImage_N. The worker classifies those
UUIDs from the same fresh project payload, preserving original slot indices;
@referenceImage_3 can bind an entity without becoming @character_1.

Characters use Q4a field10 and structured VI entity arm3, distinct from likenesses.
Actual active entity-owned projected image links and supported linked audio
metadata determine their weights. Native character/image/audio capacities are
checked before token mint or output checkpoint. Linked character audio counts
against a positive audio pool; zero audio capacity follows the frontend visual
character policy and never permits explicit audio inputs. Missing limits or
ambiguous/archived/unrelated references refuse. No entity copying occurs during
generation preflight.

This adds R2V character transport, not rendered acceptance. The free fixture
BDD passed42.07seconds with zero generation and fixture cleanup. V2V character
transport now shares fresh classification and budgets. Available direct system
presets are also audio ingredients; rendered acceptance remains R12 work. Unprojected
reference images require further ownership proof and are not guessed.

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
