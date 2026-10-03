# Existing native media metadata: measured as29s identity order

One bounded read-only original-profile capture on2026-10-03. No generation,
upload, restore, editing mutation, playback, deletion or CAPTCHA solving.
The profile was closed and explicitly released. Private structural evidence
and logs stay outside Git with mode600; public notes contain no account,
project, media, workflow, prompt, token or signed playback URL values.

A fresh selected-project `Zzl0ze` snapshot returned38assets/36timeline rows.
The chosen typed video matched an owned media/project/workflow triple and was
archived. The snapshot was persisted before selection. Navigating the measured
`/project/{project}/edit/{media}` route emitted12`as29s` metadata responses,
including the selected archived clip. Playback was disabled and one media
fetch blocked. No known resource-write request was attempted.

All12distinct returned media identities and12distinct workflow identities
crossmatch the fresh asset/timeline inventory. The current reply begins:

```text
[mediaUUID, projectUUID, workflowUUID, marker, null, DETAILS, imageArm?, videoArm?]
```

Seven replies have marker `CAE`; five have null. The selected typed-video
reply has null marker, `DETAILS[8] == [3]`, absent `videoArm[0]` and dimensions
at `videoArm[1]`. These facts do not independently establish generated versus
uploaded provenance or the meaning of every state enum.

Observed page-owned request structural envelope:

```text
f.req = [[[as29s, JSON.stringify([mediaUUID]), null, carrier]]]
```

The12request UUIDs belong to the fresh snapshot. Authentication/query values
and the carrier string were discarded. Other grid records arrive alongside
the selected item; adopting the first response would be wrong.

The existing `generation_record` decoder expects workflow/project/media
for historical submit/status records. Applying it to these current seven
`CAE` `as29s` replies swaps media and workflow on all seven. This is a
measured existing-metadata contract discrepancy, not evidence that every
submit or `jwpduf` reply changed order. No `jwpduf` response was observed;
there was no active-generation test.

Proposed next boundary: an RPC-specific existing-`as29s` decoder with mandatory
expected project/media/workflow identities and positive kind evidence from
one fresh owned snapshot. Reject mismatched, ambiguous and transposed replies;
never identify a submission by first-new-ID, prompt, timestamp or caption.
Keep the historical submit/status decoder unchanged until independently
measured. A read-only metadata service can then resolve an existing handle,
without claiming null-submit acknowledgement correlation or enabling native
video character/voice generation. Those proofs remain separate.
