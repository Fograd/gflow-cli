# Saved TTS frontend source contract

Primary source: the public gstatic AiSandboxAngularFrontend build SE3VK6s4aGU.2018.O, project modules wO1vlb and XRV0Af, downloaded without account credentials. SHA256: fde0520503cde337170e1314e9904b1da4e279d0fea2f10df7cb417ac448d31b. The public bundle is source evidence; no full bundle or private browser capture is published here.

Preview uses no0P6 (FlowService.BatchGenerateAudio), with action AUDIO_GENERATION. Request field1 repeats audio requests and field2 holds frontend context. Audio request fields:1 dialogue;2 repeated speaker pairs [preset,name];3 model gemini_v4s_tts_flow;4 performance;5 mode2. Context fields:2 client22;6 project;11 CAPTCHA [token,type1]. The generated media response is field1; exact media fields1 identity,2 project and3 workflow are checked, not the first UUID anywhere in a response.

Saving an acknowledged preview has separate operations: lt8g5 (UpdateMedia) sets media field6 metadata field10 visibility1 under the media.media_metadata.visibility mask. mYWVGd (UpdateWorkflow) sets workflow field4 metadata field1 display name and field5 project under metadata.display_name. Acknowledged preview media/workflow identities must survive a later save failure; no preview/save retry is automatic.

Custom voice deletion is source-defined by picker Delete custom voice: its asset handler emits workflow and media identities. BatchDeleteAssets cz8Z4b encodes field2 workflow identities,field3 project,field7 media identities. This is distinct from reversible timeline archive. Ownership must be verified from a fresh selected-project saved-audio snapshot before deletion.

Saved audio occupies media union field11; source classes distinguish it from image field7/video field8. The saved visibility metadata is field6.field10. Audio sample metadata fields2 performance and7 dialogue are read; signed playback fields4/6 are excluded from catalog output. Workflows supply display name and archive state. Catalog scope remains selected-project snapshot with unknown completeness.

A normal-traffic bounded UI read positively exposed Add ingredients -> Voices and sample-dialogue/performance controls, including a120-character dialogue limit. The earlier all-unknown-RPC guard was confounding; the subsequent classic-composer readiness gate also failed before the standalone picker read. A final Charon role-name selector missed before preview, so no outgoing no0P6 capture or accepted speech is claimed. No saved voice was created/deleted and no billed generation/solver request was dispatched. Runtime source-derived adapters and final E2E acceptance remain separate claims.

## Character audio binding source

The same public build character module K975Nd defines BQ with oneof fields 1, 2 and 3. BQ.Fe reads field 1 and the character display joins that value against media data. The preset selection callback explicitly writes field 2. The NS update helper stores the repeated references in CharacterInfo field 2 and uses the entity_info.character_info.audio_references update mask. Consequently saved audio uses [[media UUID]], while presets use [[null, preset ID]]. Assignment still requires fresh selected-project ownership and exact GetMedia audio-union proof; source evidence does not establish live acceptance or rendered speech.

## Preview case correction from exact source

In the cached public project bundle, t9a at character offset 3773908 sets speaker field 1 from b.Sw verbatim (setter at 3774295). The preset preview pane na accessor at 3780208 returns its displayed voice title for a preset; the RN title fallback at 3495417 capitalizes the preset name. The encoder now retains the VOICE_NAMES canonical capitalization, while accepting case-insensitive public input. The first final preview outcome was unknown and had no acknowledged media IDs; this proven source divergence does not establish the cause of that outcome.
