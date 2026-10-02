# Native project inventory: measured media union arms

## Offline evidence and boundaries

Two existing private MP4 upload captures were inspected without acquiring a browser,
issuing a request or printing identifiers, signed URLs, captions or response bytes.
Image identifiers were matched inside the inspection process to previously decoded
owned JPEG sources. MP4 identifiers came from the captured `jwpduf` ingestion
acknowledgement and were matched across captures to a subsequent `Zzl0ze` asset row.
The local synthetic input independently probes as a 256 by 256 video stream.

`Zzl0ze` outer slot 1 holds timeline workflows; slot 2 holds media records.
Observed media identity fields are `[0]` media, `[1]` project, `[2]` workflow.
Known image records have a nonnull array at slot 6, including dimensions at
`[6][2]` (known sources: 1024 by 1024 and 1376 by 768). Known MP4 records have
slot 6 null and an array at slot 7; dimensions are `[7][1][0:2]`. The upload
acknowledgement first reports 256 by 256, then an ingested rendition at 1280 by
1280. That same upload identifier is present in a later project listing with the
video arm and 1280 by 1280 dimensions. Dimensions therefore describe the returned
rendition and must not be asserted equal to original upload dimensions.

The later captured listing has 14 media rows: 13 image-arm rows and one video-arm
row. Two image-arm rows lack the observed dimension tuple. Dimensions cannot be
mandatory merely to recognize the image arm. The earlier listing has 13 rows and
no correlated uploaded video. These are capture-local counts, not account-wide
history totals. No caption/prompt heuristic was used to classify media. A generic
numeric top-level kind discriminator was not established; the mutually exclusive
union arms are the measured distinction. Unknown, both-arm and malformed records
must remain unknown or fail explicitly rather than default to image.

## Shared SDK/catalog bridge proposal

`FlowApiClient.fetch_project_listing` currently returns only the historical tRPC
`result.data.json.projectContents` envelope, through the API request context.
`catalog_sync.parse_project_listing` expects that envelope, takes presence from
`media[].name`, joins names through workflow primary media identifiers and marks
completeness from pagination marker keys. Names are prompt-derived and remain
subject to the existing `history_prompts=redacted` refusal. The sync seam is
synchronous, marshalled onto the existing async client loop by CLI callers.

A native port should reuse the existing client and one leased page to read the
measured project payload, then return an explicit native listing DTO/parser result
rather than inventing a historical Google envelope. Pure parsing can join every
validated media record to its validated project/workflow; kind comes from the
exclusive union arm. Names must retain control-character scrubbing and the privacy
gate. Captions belong to workflows and must not be relabelled as prompts. Attached
character-copy media and preset voices must not silently count as generation history.
All measured asset rows provide positive presence, even when no timeline workflow
exists. Recognizing image/video arms does not establish generated/uploaded origin,
model names, timestamp semantics, seed fields or account-wide exhaustive history.

## Predict verdict

**CAUTION / 8 of 10.** A native read/parser port is feasible and credit free.
It introduces project navigation instead of the historical roughly half-second
request-context fetch; sequential sweeps must budget one page checkout and current
bounded navigation/response waits per project, preserving the existing cadence and
no nested client/profile lease. Do not use concurrent navigation on a shared page.

Security: validate all project/media/workflow UUIDs before construction, bound
response bodies, discard signed URLs, log identifiers/counts only and retain the
caption privacy gate. CLI/MCP should share the catalog service and typed parser.
Completeness and pagination of `Zzl0ze` have not been measured. Initially set native
completeness false: positive presence can clear ghosts, but absence cannot safely
mass-tombstone. A complete flag requires a separate observed pagination contract.

The next implementation scenario should cover mixed image/video arms, missing
image dimensions, unknown/both arms, unattached media presence, malformed ownership,
control-character captions and partial-list ghost refusal. An opt-in free browser
scenario can compare the known synthetic upload and known decoded image to actual
read-only listing output; no fresh generation is necessary. This evidence file is
research only; no production source was changed.
