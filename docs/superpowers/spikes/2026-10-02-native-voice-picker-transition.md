# Native voice picker transition: inconclusive metadata binding

## Question and boundaries

Can a system preset be assigned to an existing character with empty dialogue and
performance fields, without generating TTS? Historical upstream evidence verifies
free Bearer metadata assignment, but does not establish today's migrated RPC.
A metadata acknowledgement and nonempty authoritative audio slot would establish
attachment; a selector/transition miss establishes neither support nor absence.

## Observations

Two bounded probes used separate temporary image-backed characters, copied from an
owned existing image. The native picker exposed 30 presets, sample dialogue,
performance controls and an add-to-character affordance. Charon was selected and
both textareas explicitly cleared. The selected preview-pane button candidate was
enabled, but the probe did not independently verify that this candidate was the
actual add-to-character control. It must therefore be treated as an unverified
selector transition.

The first probe's authoritative character audio slot remained null. In the second,
the preset was absent from the character UI and the picker stayed open. The header
Done control was present but its attempted click was intercepted by the modal
backdrop. No native voice metadata commit was observed. No `rzMKMb` voice update
was captured. Unknown `WuwhI` requests were aborted; their purpose was not
established and they are not labelled as voice generation or telemetry.

The route guard permitted only previously observed read/metadata RPCs and aborted
unknown RPCs and nonmetadata writes before submission. No TTS/image/video generation
or solver task was submitted. Both temporary characters were deleted through the
verified owned-entity cleanup adapter. No production implementation was changed by
these probes; public evidence contains no account/media identities or signed URLs.

## Reading and next experiment

**Inconclusive.** The probes did not complete the picker-to-character transition,
so they do not test a committed voice assignment and cannot justify a claim that
Google lacks it. Current REST voice assignment/custom voice operations remain
unimplemented, rather than proven unavailable on Google.

The next free experiment should inventory the open dialog's custom elements,
button classes, icon structure, disabled state and occlusion before clicking a
verified add-to-character footer control. Then observe the structural Done commit
only after the dialog has actually closed. Continue blocking every unclassified
write until its cost and purpose are established. Custom TTS creation needs a
separate measured contract and generation authorization; preset metadata attachment
and rendered voice/audio application are separate verification claims.
