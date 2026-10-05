# System presets and saved TTS voices

System presets are already available through bundled offline lookup and dynamic native SDK/CLI/MCP/REST reads. Thirty preset names were measured. Preset assignment to a character changes metadata; it does not prove generated speech.

Saved TTS is a different native flow. The exact deployed Angular project bundle exposes a preview operation named BatchGenerateAudio, with native RPC no0P6, action AUDIO_GENERATION and model gemini_v4s_tts_flow. Its UI accepts sample dialogue, a performance description and a voice name. Playback resolves the generated media through GetMedia. Saving the preview then performs two metadata mutations: UpdateMedia (lt8g5) changes media visibility, and UpdateWorkflow (mYWVGd) saves the display name.

These source definitions establish that the flow is preset-based speech generation followed by saving metadata, not voice cloning. The5 October follow-up below supplies successful frontend request and existing saved-voice playback evidence. Earlier investigation statements describe their original checkpoints. The fork implements these source-derived native operations through SDK and a shared service; REST/MCP adapters are wired. Final live acceptance is intentionally deferred to the end of feature implementation. A normal-traffic picker read exposed the voice controls, but the final preview selector missed before dispatch, so no outgoing or accepted TTS proof is claimed.

The first private menu reads used an overbroad request guard and are therefore confounded. They cannot establish that Google lacks saved voices. A corrected probe must allow normal metadata/preferences traffic while blocking known billable/resource mutations. Only the final intended creation gesture may arm a broader write abort to capture the request without generating speech.

During the original source investigation, no saved voice was created or deleted and no paid TTS or solver task was submitted. The later final preview attempt is recorded below; its outcome was ambiguous. Existing voice identities must never be used as deletion fixtures. Saved user voice list/detail/delete and accepted creation remain separate proof obligations; system preset lookup and assignment continue to work independently.

## Public commands and recovery

~~~bash
gflow voice list --project PROJECT_UUID --profile PROFILE --json
gflow voice show --project PROJECT_UUID --id VOICE_UUID --profile PROFILE --json
gflow voice create --project PROJECT_UUID --name "Guide" --preset Charon --dialog "Hello" --performance "Warm" --profile PROFILE --json
gflow voice rm --project PROJECT_UUID --id VOICE_UUID --confirm-delete --profile PROFILE --json
~~~

Creation can consume credits. It validates dialogue/performance lengths1–120 and voice-name length1–200 before browser access, then performs one preview and two metadata saves. Saved voice deletion is permanent native BatchDeleteAssets, distinct from reversible media archive. System presets fail saved-media ownership preflight and cannot be deleted through these commands. List is a selected-project visible saved-audio snapshot with unknown completeness; detail can return a fresh HTTPS audio URL after exact ownership checks.

VoiceMutationUnknownError uses exit40, nonretryable guidance and safe acknowledged media/workflow handles. Save failure preserves the generated preview identity for inspection instead of repeating speech generation. Cancellation remains cancellation with typed recovery metadata. No automatic preview/save/delete retry occurs. The catalog contains no signed URLs; detail playback URLs should not be copied to public logs.

Focused source-codec/parser and single-attempt transport tests pass; accepted live creation/deletion remains unverified. No paid TTS or solver task was submitted while implementing these adapters.

## Saved voice character assignment

Character create-from-images and update accept a saved audio media UUID in the existing voice argument, alongside system preset names. Before changing a character, the native adapter requires the saved voice to appear in the active selected-project catalog and verifies its exact media/project/workflow identifiers through GetMedia with an exclusive audio union. The character stores the saved media reference in audio reference field 1; preset references retain field 2. Saved UUID readback is preserved. This source-derived binding is implemented and tested offline; live assignment and rendered speech remain unverified. Vendor composite user-voice references must first be resolved to their media UUID.

## Preview preset capitalization correction

The audio preview request preserves the canonical displayed system preset name, such as Charon. Public CLI/SDK input remains case-insensitive. This differs from character preset metadata, whose measured identifier remains lowercase. A first final TTS attempt returned an unknown preview outcome without acknowledged media IDs. Source inspection corrected the preview encoder's lowercase divergence; that difference is not established as the cause. The separately authorized corrected canonical Charon trial captured one no0P6 request and received explicit PUBLIC_ERROR_UNUSUAL_ACTIVITY, gRPC 7. Its test reported one failure and four skips in 17.93 seconds. No audio or saved-voice binding lifecycle was accepted.

The completed controlled CapSolver trial concerned native VIDEO_GENERATION, not saved TTS. Its one solved token and one submission were Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7), with no accepted output or retry. It does not verify audio preview tokens or saved-voice creation. The corrected canonical Charon request was captured once and explicitly Google-rejected with PUBLIC_ERROR_UNUSUAL_ACTIVITY (gRPC 7). No accepted audio or binding lifecycle is claimed.


### Fresh saved user voice detail
Saved-TTS detail now exposes a recognized canonical base preset from the native
audio preset/speaker fields, freshly read dialogue/performance and optional audio
playback URL. A separate description remains separate from voicePerformance.
SDK get_saved_voice, CLI voice show, direct MCP gflow_get_saved_voice and REST
GETvoices/ref source=user share the decoder. Strict GetMedia matching verifies the
selected project/media/workflow and exclusive audio arm. Playback URLs are
confidential HTTPS values from the owned native response; no media fetch or
unverified universal URL lifetime is implied. REST returns no-store.
Missing playback remains optional; missing inventory is not proof of deletion.
The original selected-project checkpoint had no saved-user fixture. The5 October
follow-up below closes existing-voice lookup/playback proof; backend creation and
the full mutation/binding lifecycle remain separate R12 acceptance requirements.

Saved-voice `voice create` and direct MCP `gflow_create_saved_voice` now accept optional
provider order/total-attempt controls. The SDK `saved_voice_operation` bridge exposes the
same controls for `create` only; list/get/delete refuse them. Existing browser defaults
and accepted-preview/unknown-save no-replay rules apply. See
[native provider controls](NATIVE_CAPTCHA.md#saved-voice-and-promotion-clidirect-mcp-provider-controls).


R02 read-only delivery on4October found no saved-user voice in either selected
pro2/pro3 project. Detail/playback remains implemented across SDK/CLI/MCP and REST,
but this run supplies no accepted saved-user playback proof. Both accounts have
used their original three authorized previews. A subsequently authorized single
additional pro2 preview returned NativeQuotaError without accepted output or
retry; the observed credit balance remained1050. Saved-user playback proof is
still unavailable, and no URL is invented.
An existing owned saved voice in an explicitly selected project can be read without
creating a new preview. Missing playback remains optional, never a synthesised URL.


Saved voice show/detail accepts a native audio media UUID or an exact locally
registered voice alias. SDK get_saved_voice, CLI voice show --id and direct MCP
saved voice detail require the owning selected profile/project. Alias reads must
run against the same private GFLOW_SELFHOST_ROOT as REST, using an enabled verified
registration; unknown vendor references are not decoded. A fresh native audio
read must match the registered media/project/workflow. Optional description,
performance, dialogue and playback metadata are retained across adapters; REST
uses description, voicePerformance, dialog and audioUrl. Creation, deletion and
character mutation inputs keep their existing raw contracts.


## Existing saved voices: verified lookup and creation limitation

On 5 October 2026 an operator-created Charon saved voice passed SDK, CLI, REST and
registered HTTP MCP detail reads. Its exact locally registered alias passed all
four adapters, with fresh selected-account/project/media/workflow validation.
REST through Mac localhost returned 200 with Cache-Control:no-store. The returned
Google audio URL played a valid 7.8-second mono 24 kHz PCM WAV (374,444 bytes).
Dialogue, preset and the performance description were preserved. Native
performance and description are separate optional fields; no missing value is
synthesised. The original voice remains saved; only the temporary alias was removed.

Use an explicitly selected project/profile:

~~~bash
gflow voice show --project "$PROJECT_ID" --id "$VOICE_MEDIA_ID" --profile pro2 --json
~~~

The shared SDK service also selects the profile explicitly (inside an async function):

~~~python
from gflow_cli.services.native_voices import saved_voice_operation

detail = await saved_voice_operation(
    profile="pro2", operation="get", project_id=project_id, voice_id=voice_id
)
~~~

For direct MCP call gflow_get_saved_voice with project, voice_id and profile.
voice_id may instead be an exact registered alias. REST uses
GET /v1/google-flow/voices/REF?source=user&email=REGISTERED_ACCOUNT&projectId=PROJECT_ID
with the existing bearer credential. Google principals and REST registration
handles are distinct; obtain the selected handle from GET /accounts.
See [exact voice alias registration](API.md#explicit-character-and-saved-voice-aliases).

**Backend creation limitation:** voice create, gflow_create_saved_voice and POST
voices are implemented, but the tested backend previews were Google-rejected with
PUBLIC_ERROR_UNUSUAL_ACTIVITY. Frontend creation succeeded in 21.19 seconds using
matching preview/save payloads. A 90-second experimental request deadline still
received rejection in 0.45 seconds. The rejection criterion is unknown; it is not
proved to be a Pro-plan or credit restriction. Session/token trust and network
reputation are hypotheses. No speculative wrapper change was shipped and no
further preview retry is needed for lookup. Backend creation, deletion
acknowledgement and character/audio binding acceptance remain R12 limitations.
An uncertain deletion must be checked with fresh inventory, never automatically
replayed. Existing-voice playback verification does not establish the full CRUD lifecycle.


R04 video references accept saved-user audio UUIDs, supported generic native audio
UUIDs without saved visibility, and fresh available system presets through distinct
ownership/catalog checks. Generic audio is not a saved voice: saved-voice lookup
and aliases still require the saved-user contract. No preview is needed to reference
an existing voice. The existing-audio R2V/V2V final request preflight passed before
token minting with the original voice preserved; speech/grounding remains R12.
See [reference inputs](NATIVE_REFERENCE_VIDEO.md#r04-supported-reference-inputs-and-implementation-closure).
