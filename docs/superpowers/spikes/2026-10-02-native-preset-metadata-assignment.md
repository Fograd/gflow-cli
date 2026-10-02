# Native system preset metadata assignment

The previous picker probe used a preview-pane button. A structural inventory now
positively distinguishes Preview (`play_arrow`, inside `flow-voice-preview-pane`)
from the actual footer, `flow-add-menu-detail-pane .bottom-actions >
button.detail-add-to-prompt-btn`. The footer was unique, enabled and unobscured;
its center hit a descendant label. Clicking it removed the dialog. Only then did
the structural character header Done button commit the change.

With empty dialogue and performance fields, Done emitted metadata RPC `rzMKMb`:

```text
[[PROJECT, ENTITY, null, [1, null, [null, [[null, "charon"]]]]],
 [["entity_info.character_info.audio_references"]]]
```

The correlated RPC returned HTTP 200 with the same measured audio-reference
shape. The first fresh project read had a null audio slot; the second contained
`[[null, "charon"]]`, and a final read agreed. This demonstrates eventual visibility,
so sent-request evidence alone is insufficient. The probe selected the exact owned
entity for authoritative readback. Explicit acknowledgement identity correlation
is enforced by the implementation rather than inferred from a successful status.

The temporary image-backed character was deleted. Unknown native writes and every
TTS/image/video submission were blocked; no speech was generated and no solver
was called. Lowercase preset identifiers differ from the historical Bearer API's
canonical names. Only known system presets present in the current project catalog
are accepted. Clearing an audio reference and custom saved TTS remain unmeasured.
Metadata attachment does not establish that a generated video applies the voice.

Implementation tests cover exact field masks, canonical/lowercase mapping,
unknown/empty inputs, malformed/custom audio getter compatibility, wrong-entity
acknowledgements, stale-read polling and preservation of name, image workflows and
personality. Mutation acknowledgement plus bounded fresh visibility checks share
one 45-second deadline. A post-write failure retains the known character identity
and does not replay the mutation. Creation performs this after image copying,
inside the existing shared postcreation deadline.

The opt-in `@e2e @e2e_data` adapter scenario passed in 65.12 seconds. It created one
owned temporary character with two image references, initial personality notes and
Charon, then changed the preset to Aoede. Exact acknowledgement and authoritative
visibility were checked by the driver. Name, notes and copied workflows were retained;
both source images stayed active. Cleanup confirmed the test entity absent. The
scenario aborts unclassified writes and generation before submission.

A follow-up notes-clear probe identified an acknowledgement normalization bug:
requesting `personality=''` succeeds natively, but Google omits the notes slot,
which the parser represents as `None`. Fresh reads alternated clear/old/clear,
so the driver now recognizes null/absent as canonical empty only for an explicit
notes clear, then requires two consecutive clear reads within the same 45-second
post-write deadline. It does not repeat the write. Public SDK personality remains
`None` for absent notes; REST presents absent notes as an empty `personalityNotes`.
This canonicalization concerns notes only and does not treat absent audio as a
voice clear. The follow-up metadata-only BDD passed in 69.90 seconds: two references,
initial Charon and notes, explicit notes clear, Charon/name/copied workflows retained,
both source images active and owned character cleanup confirmed. No speech generated.
