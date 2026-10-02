# Native MP4 upload and project media archive

## Prediction and security review

The migrated image uploader listens for `maseQ`; a video picker accepting MP4 does
not prove that listener can ingest video. Measure a self-created synthetic fixture
before adding an API contract. Keep profile leases, reject arbitrary URLs, validate
file size before allocating bytes, correlate upload responses to the chosen project,
and validate every deletion identifier before sending any mutation. Google Pro
credits must not be spent for these resource probes.

## Measured surface

The Flow toolbar file chooser accepts image and video suffixes. A one-second,
256×256 H.264 synthetic colour MP4 uploaded through the native chooser. The video
rights confirmation is separate from the image confirmation. The probe accepted
once for its own generated fixture; production defaults to an actionable pending-rights error. An explicit per-request
`rights_confirmed=true` ownership assertion allows only the third (agree once) button
in the measured three-button dialog. It never changes persistent account preferences.

Video ingestion uses `/upload/v1/flow/upload/video/<project>` and responds with
JSON `mediaId` plus `media.name`, `media.projectId`, and workflow metadata. The
resumable initiation response is empty; the final response contains the record.
Consequently the old image listener times out despite a successfully uploaded clip.
The new video driver observes this separate endpoint and validates record/project
identity. MP4 validation and the 250 MiB cap are local guards, not advertised Google
limits or codec compatibility guarantees.

Project navigation emits `Zzl0ze` with arguments
`["projects/<project>", null, null, null, [1]]`. Its timeline row has workflow ID at
`[0]`, project at `[4]`, caption at `[3][0]`, media ID at `[3][4]`, and archive state
at `[3][2]`. Asset records expose media/project/workflow identities at positions
0/1/2; these correlate each batch's media membership. The service returns this
project timeline without guessing a media type or claiming attached-asset/history
pagination parity. Imported assets and generated images were both present.

Clicking Trash batch on an owned synthetic video emits `pGCYOe`:

```json
[[["<workflow>", null, null, [null, null, 1], "<project>"]],
 [["metadata.archived"]]]
```

This archives a batch reversibly. It is not an individual-media permanent delete.
The adapter refuses partial batch selection, unrelated project ownership, duplicate
or malformed IDs, unknown batch membership, and requests outside 1–100 entries before sending the mutation.
Every requested workflow must be acknowledged with archive state `true` and the
matching project. Missing acknowledgement means unknown/partial outcome: inspect
state before retrying. No automatic write retries are performed.

## Contract and verification

Private worker: `python -m gflow_cli.selfhost.native_worker VERB PROFILE JSON_PAYLOAD`.

| Verb | Input | Result |
| --- | --- | --- |
| `upload-video` | `project_id`, contained local `path`, optional `rights_confirmed` boolean | `media_id`, `project_id`, unique `caption`, `kind=video` |
| `media-list` | `project_id` | `media`: IDs, caption, archive state, batch membership |
| `media-delete` | `project_id`, `media_ids` | `deleted`, `operation=archive` |

REST resolves managed file ownership before worker dispatch. The worker uses the
normal authenticated browser profile lease and honours the legacy-host kill switch.
Pending consent is a structured `upload_rights_required` error; REST accepts the
explicit ownership assertion through `X-Flow-Rights-Confirmed: true`. No public CLI
or MCP mirror was added by this change.

Sixteen focused offline cases validate MP4 header rejection, upload identity/project
correlation, timeline identities, complete batch validation, and refusal to archive
unrequested siblings. Strict Pyright and Ruff passed for these new modules. The scenario-bound native
resource BDD then passed live in 32.07 seconds, including unattended upload with
explicit per-request rights confirmation. The first live BDD exposed a real reader
race: an aborted response from a previous navigation was treated as a new read
failure. The reader now filters the Zzl0ze RPC and ignores unavailable bodies from
aborted navigation responses; malformed current timeline payloads still fail.

The actual native driver uploaded a synthetic one-second video, obtained its exact
returned media ID through a subsequent timeline read, archived it through the new
RPC helper, and confirmed archive state on a fresh native read. Earlier synthetic
probes were also archived. No image or video generation was submitted or charged.
Upload and archive acknowledgements precede timeline visibility: live verification
needed short additional navigations after successful operations. Callers must allow
this eventual consistency and must not repeat successful uploads as a polling step.
Private wire captures and fixtures remain in the gitignored spike directory; no
session material, account identifiers, or project identifiers are published here.

## Remaining evidence gaps

Global project/media history pagination, attached-asset merge rules, individual
media deletion within multi-output batches, character CRUD, saved voice generation,
and video extension require their own observed contracts. This change does not
claim those useapi features are unavailable or implemented.

## Character and saved-voice read probes

Current toolbar Create character navigates to `/project/<project>/character`,
without creating an entity. The initial page contains portrait presets, a prompt
editor, an Upload affordance, and Add from project. Opening the project picker
shows Images/Uploads tabs and a Search assets field. No voice tab or metadata
editor was present on that initial creation surface. The historical upstream
character editor does expose name/personality/voice controls, so this initial
page is not evidence that character or saved-voice CRUD is unavailable.

A follow-up binding probe guarded all generation RPCs with aborts and attempted
to select an existing older test image. Its button was absent from the virtualised
picker, so it ended before selection or mutation. The bounded follow-up filled the picker search input and also tried current
asset-item button anchors; it still ended before selection. The remaining
blocker is unmeasured picker selection topology and editor transition. A future
probe must inspect the actual selectable element ancestry, bind an owned image
without generation, and measure the resulting editor and save contracts. These
selector misses do not demonstrate missing character or saved-voice capability. No character/voice entity was
created or deleted during these read probes. A brief home navigation observed
user-preference RPC `xI9TVb`; it did not establish global project listing or the
`UpteDb` contract found in another implementation.

A fixture left by the first failed resource BDD was discovered in the native
timeline and archived during final probe cleanup; no failed-test synthetic video
remains active. The successful BDD also archived its fixture before passing.
