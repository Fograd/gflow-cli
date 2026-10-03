# Image aspect and inline grounding: measured frontend contracts

Served host: flow.google.com. One authenticated Pro profile, one existing project.
All image generation RPCs were intercepted and aborted before Google acceptance.
Unknown writes were aborted; no image/video/TTS generation or solver task ran. Native
browser reCAPTCHA traffic was allowed; tokens, account IDs and signed URLs are omitted.

## Actual aspect panel

The positive panel observation uses `.settings-trigger-button` in
`FLOW-BASE-PROMPT-BOX`: one enabled button, icon `crop_square`, center hit-test inside
the button. Mouse click alone did not reveal the panel in this run; keyboard Enter on
the same focused button did. The opened component was `FLOW-PROMPT-BOX-SETTINGS`,
containing `FLOW-TOGGLES` / `MAT-BUTTON-TOGGLE-GROUP[role=radiogroup]`.
The five offered ratios in the tested Nano Banana 2 / one-reference case were:

| Ratio | Icon |
| --- | --- |
| 16:9 | crop_16_9 |
| 4:3 | crop_landscape |
| 1:1 | crop_square |
| 3:4 | crop_portrait |
| 9:16 | crop_9_16 |

No Auto control was observed in that opened panel. This is evidence about those
rendered controls, not proof Google lacks another automatic-aspect contract.
The SDK's existing explicit Aspect enum and migrated map contain those five values;
no measured Auto/unspecified sentinel is available to port.

The local policy `derived-first-reference-nearest-supported-v1` preserves exact
supported ratios, otherwise minimizes absolute logarithmic distance from the first
actual reference image's decoded width/height to those five ratios. This is explicitly
a local approximation; the exact Google/useapi internal selection algorithm is unknown.
Ties use declared order: 1:1, 4:3, 3:4, 16:9, 9:16. File validation accepts decoded
PNG/JPEG up to 20 MiB and 25 megapixels. Character entities alone are not an actual
reference image. Callers retain requested `auto`, resolved explicit ratio and policy.

## Image inline media chunks and deduplication

Two mentions of the same existing recent image bound as two `media` chips.
The outgoing `ogiZ0b` was captured and aborted. Each request row has:

```text
row[2] = [[MEDIA_ID, null, null, null, 1]]
row[4] = 1
row[8] = [[[null, [[MEDIA_ID, DISPLAY_NAME]]], [TEXT_CHUNK],
           [null, [[MEDIA_ID, DISPLAY_NAME]]], [TEXT_CHUNK]]]
row[9] = null
```

The two ordered inline media chunks remain; the reference vector is deduplicated to
one image in row[2]. The first existing source was a decoded 1024×1024 JPEG, so the
local decision resolves to 1:1; the actual outgoing square aspect scalar was `1`.
This abort proof establishes outgoing structure, not a completed new generation.

## Image inline character chunks

One owned temporary character, bound to a copied existing image through the verified
metadata-only character helper, was mentioned via the native picker. The committed
chip had `data-reference-type=entity` and exact matching `data-entity-id`. The captured
and aborted image request used:

```text
row[8] = [[[null, [null, null, [ENTITY_ID, DISPLAY_NAME]]], [TEXT_CHUNK]]]
row[10] = [[ENTITY_ID]]
```

This positively establishes image character grounding. The temporary entity was
deleted in cleanup. It does not establish video character completion: the previously
captured null/status-only video acknowledgement needs a separate terminal observer.
Repeated entity chunks have not yet been measured; do not infer their deduplication
from the repeated-media result.

Private scripts/logs retain redacted structural evidence outside tracked source.
No public document includes account/profile/source UUIDs, token values or signed URLs.

## Implementation and current verification boundary

The implementation adds strict parsed pre-submit correlation for image entities and
positional reference plans. It materializes literal text spans and identity-checked media
or character chips in order; a logical local source ID maps to the media ID and unique
name acknowledged by its upload. Repeated markers remain repeated chunks; unmentioned
attachments are prefixed. Unknown paragraph/chunk/vector shapes refuse before allowing
Google submission. Ordinary video attachment calls retain their existing behavior.

Offline tests verify exact ordering, repeated media deduplication, rejection of bare text
substitution, wrong entity/name/project, unknown chunks, additional/missing vectors and
mapping logical local IDs to actual uploaded identities. They do not establish that the
current frontend materializes every canonical prompt shape; that still needs a fresh
abort-only capture.

One count-one native image BDD was attempted after explicit authorization. It reached
Flow's public `/about` landing before creating any fixture or submitting a generation;
the repository's existing public-landing E2E hook reported a skip. No generated-media
checkpoint exists. The follow-up read-only probe confirmed the landing and failed to read
the native project. Navigating the page's observed Google sign-in link revealed one
account chooser row. Its identity matched the profile's recorded principal privately;
authorized selection reached a Google identity-challenge route, with no email/password
input or Flow editor in the inspected state. No challenge automation was attempted.
All probe contexts closed and the profile lease was released.

This establishes an authentication precondition blocker for the next live proof, not its
cause and not absence of image/marker capabilities. The one-image test allowance remains
unused. Native entity completion and canonical positional materialization remain live
verification pending; no video/TTS generation or solver task was used.


## Restored-session canonical abort observations

Manual authentication restored native project access. A fresh client context using the
same original profile then completed free project reads and owned character create,
image-copy binding, and deletion. This demonstrates persistence over that reopen; it
cannot guarantee Google's future session lifetime.

For `Draw @reference_1 beside @character_1 and @reference_1.`, the native picker
produced the expected two ordered media chips and one character chip, with deduplicated
media/entity vectors. It also inserted one ASCII space after each chip: outgoing
literal spans became `  beside `, `  and `, and ` .`. The strict positional guard
refused the request before submission. Both investigation fixtures were cleaned up.

The materializer now removes only a verified collapsed caret on an exact single-space
text node within the composer, immediately after committing a chip; subsequent chip
identity/count and full wire equality checks still gate submission. Caller-authored
literal spaces are preserved. Unrecognized caret shapes fail closed. The focused
separator tests passed red-to-green; live corrected abort proof passed.

The corrected probe reached the post-guard callback, proving the production ordered
chunk guard accepted the exact original literal spans plus repeated image/character
bindings and deduplicated vectors. The callback deliberately raised before route
continuation, so Google generation remained blocked. Its owned fixture was deleted.
Acceptance is separate from this transport evidence.


## One accepted SDK image proof

The bound native-image BDD passed once in 104.75 seconds after the corrected abort
proof. Its sole count 1 request used the SDK's fresh native ownership/weighted reference
validation and single-attempt browser transport. The prompt contained two occurrences
of the same image marker plus one owned character marker. The production guard checked
all ordered literal/reference chunks and deduplicated media/entity vectors before the
scoped allowance authorized exactly one unchanged native browser request.

The first owned reference decoded as square, so the explicitly labeled local
first-reference policy resolved `auto` to `1:1`; the outgoing measured aspect scalar
was 1. Google returned one image. Its downloaded JPEG decoded at 1024×1024 pixels,
270277 bytes. Remote media/workflow recovery handles were checkpointed privately before
download. The temporary character was deleted in cleanup; the original source images
were retained. No solver task, video generation, or TTS generation was attempted.

This proves the tested SDK image path and its grounding envelope, not semantic fidelity
of generated objects, every possible paragraph/chip shape, other model reference caps,
CLI/MCP/HTTP billing paths, or Google's future authentication lifetime. Normal client
reopenings of the original profile retained project access following manual login.
Adapter owners must retain the same immutable plan and fail-closed boundary checks.
