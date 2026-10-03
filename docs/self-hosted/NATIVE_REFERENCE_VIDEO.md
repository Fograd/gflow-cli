# Native video with image, audio and character ingredients

The native reference-video adapter encodes Flow's deployed Q4a/MZZa6b request. SDK, CLI and worker implementation is tested offline. **Google generation acceptance remains pending final E2E.** Existing image/audio UUID ingredients must belong to the selected project and appear with the correct exclusive native media type in a fresh snapshot.

Discover current account-tier model keys:

```sh
gflow video reference-models --project PROJECT_UUID --with-audio --profile pro1 --json
```

Generate from ingredients, using a discovered key:

```sh
gflow video reference-native --project PROJECT_UUID --profile pro1 \
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
transport now shares fresh classification and budgets; direct system-preset audio
and rendered acceptance remain subsequent R04/R12 work. Unprojected
reference images require further ownership proof and are not guessed.
