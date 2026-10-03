# Native media detail completion implementation plan

**Goal:** Finish bounded R02 typed audio and character-thumbnail adapters while pairing fresh generated-output reads with R03 membership.
**Architecture:** Reuse one fresh project payload and strict correlated GetMedia. Add a separate audio DTO with absent dimensions; retain the measured image/video-only downloader. Existing SDK/CLI/direct and queued MCP/HTTP adapters share services.
**Predict verdict:** GO for exclusive media classification and bounded thumbnail extension; CAUTION for audio download and composite translation until measured contracts exist.

## Tasks
- [x] Red tests: generic audio, exclusive union, owned active workflows and metadata-only download refusal.
- [x] Core typed audio and shared classification; strict thumbnail candidate resolution.
- [x] Mirror adapter help, HTTP audio rejection and documentation; six axes per skills/check/SKILL.md.
- [x] Live generated image and character reads, offline full gates and source boundary review.
- [ ] Publish/deploy this batch; continue verified composite mapping and R03/R04 requirements.
- [ ] Continue verified composite mapping and R03 inventories, then accepted R04 video references.

## Risk register
| Risk | Mitigation |
|---|---|
| Signed playback URL used as unrestricted downloader | Audio metadata only; explicit pre-network refusal |
| Partial projection treated as deletion or ownership evidence | Fresh unique workflow joins; no absence-based deletion |
| More generation than user authorized | Durable locked per-account 50-image/2-video ledger; ambiguous submissions count |

## Definition of done
Full gates and appropriate tagged E2E pass; public docs distinguish implementation from accepted outputs. R02 remains unchecked until composite mapping and remaining detail/error requirements are met. Standing user approval authorizes execution without another plan confirmation.

## Six-axis check
A/B: Shared synchronous services propagate SDK/CLI/direct MCP/native worker metadata; lookup/download tools execute directly, no queued signed-URL result added. Existing generation worker codec is unchanged.
C: README, AGENTS and canonical/plugin skill updated. D: Existing WireFormatError mapping reused; HTTP audio is explicit400 after matching IDs. E: No template, environment or generation default changed. F: MCP/USAGE/API/native-media/changelog updated and website mirror regenerated.
Inventory counts cover observed timeline/attached UUID media, excluding verified bundled presets. Foreign attachment listing never widens mutation ownership.
