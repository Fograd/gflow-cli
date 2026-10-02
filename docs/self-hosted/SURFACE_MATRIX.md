# Implemented surface audit

Current source audit: 2026-10-02, including the SDK/CLI/MCP expansion after published two-reference snapshot `acd0d69b15`. Live proof is listed separately for each surface. Implemented code with pending proof is explicitly marked; gaps do not imply Google lacks the operation.

REST source is `src/gflow_cli/selfhost/server.py`; its isolated native worker is `selfhost/native_worker.py`. Existing SDK entry point is `api/client.py`; CLI files are `cli_character.py`, `cli_project.py`, `cli_image.py`, `cli_video.py`; MCP is `mcp/tools.py`; queued image/video decoding is `worker/codec.py`. Paths are relative to `src/gflow_cli/` unless prefixed with tests.

| Feature | REST/native fork | SDK / CLI / MCP / queued caller audit | Proof / missing work |
|---|---|---|---|
| Character creation from one/two existing images | POST validates registered decoded references/account/project and native active membership; copies portrait/body with optional notes/preset | SDK `create_character_from_images`; portable `services/native_characters.py`; CLI `character create-from-images`; MCP matching twin. Shared service requires verified local PNG/JPEG catalog copies, not REST registration. Older generated-portrait create remains separate. No queued CRUD. | Native two-ref 34.11s / HTTP two-ref 97.82s proof and updated HTTP preset/clear 123.99s; native preset 65.12s. Actual CLI and MCP full lifecycle BDDs passed after measured notes-clear repair. |
| Character list/detail | Native project summaries/details expose stable IDs, notes and preset metadata | SDK `list_characters/get_character` dispatch native migrated host while retaining legacy dispatch; CLI list/show and MCP existing twins share SDK. | HTTP catalog/detail proof. Actual CLI/MCP list/show lifecycle BDDs and updated HTTP preset/clear 123.99s passed. |
| Character metadata update | PATCH name/personality/preset; native acknowledged values | SDK `update_character`; CLI `character update`; MCP twin share bounded service and pure validation before profile/browser. Empty notes clear is implemented and the native acknowledgement repair is live verified. | Native clear repair in 69.90s and actual CLI/MCP clear/rename/notes/Charon→Aoede lifecycle proof passed. |
| Character removal | DELETE owned project entity, fresh visible removal/404 | SDK native delete dispatch; CLI rm and MCP `gflow_character_rm` pre-read exact identity. MCP requires `confirm_delete: true`; unattended CLI uses `--yes`. Typed unknown outcomes are nonretryable. | HTTP/native deletion proof; both failed first CLI/MCP lifecycle test fixtures were cleaned through the new MCP removal surface. Full CLI/MCP lifecycle rerun passed with confirmed owned-entity removal. |
| Character reference/voice grounding | Two source copies and system preset metadata assignment implemented | SDK/CLI/MCP create/update support case-insensitive system presets; old generated saga retains its options. Entity attachment to subsequent generation remains separate. | Native and deployed HTTP Charon→Aoede/clear persistence proofs. Rendered speech, custom voices and character generation grounding remain unverified or unported. |
| Account project discovery | Explicit source=google native opaque pages of 21/cursors up to 4096; local default remains | SDK `list_native_projects(cursor)`; CLI project list --source google --cursor; MCP gflow_list_projects source/cursor. Native rejects caller page limits; local JSON fields preserved through shared project_output helper. | Native/HTTP disjoint-page proof. Actual CLI/MCP two-disjoint-page BDD passed; strengthened SDK 21+21 BDD passed in 11.42s. No local catalog sync claim. |
| Project media inventory | Native selected-project timeline; default managed cache stays separate | SDK `list_native_media(project_id)`; CLI project media and MCP gflow_project_media read native asset snapshot including image/video/unknown kinds and measured dimensions. `complete: null`; no caption/signed URL or absence deletion. Legacy catalog sync remains separate. | Native timeline worker 32.07s proof; typed mixed-asset parser offline tests. Actual CLI/MCP image/video kind agreement BDD passed; strengthened SDK mixed-media BDD passed in 11.42s. |
| Media deletion/archive | Native reversible whole-batch archive or explicit localOnly cache deletion | Private worker-only measured operation; legacy asset endpoints/CLI surface are not an integrated native archive mirror. | Native worker proof; whole-batch ownership/acknowledgement. Individual already-gone useapi semantics remain different. |
| Raw image/MP4 upload | REST raw upload, 20MiB; MP4 explicit per-upload rights header | Image CLI upload exists; native MP4 worker is separate, no public SDK/CLI/MCP upload-video mirror in this audit. | Native MP4 worker BDD 32.07s. Do not treat saved local video as native media ID; no account-wide consent. |
| Native image upscale | REST /images/upscale; shared native migrated upscale in SDK | CLI image upscale and MCP gflow_upscale_image share FlowApiClient native path; original MCP/CLI public twins exist. Not a generation queue operation. | Live CLI/HTTP/MCP 2K, Pro 4K refusal. Actual Ultra 4K success unverified. |
| Native video export | REST upscale/GIF adapters and shared native transport | CLI video upscale and MCP gflow_upscale_video present; exports are direct operations, not queued image/video generation codec. | Offline proof; live generated-video exports not yet verified here. Original 720p download is not 360→720 promotion. |
| Native image seeds | REST guarded ogiZ0b override and returned-seed checks | GenerateImageRequest.seed ->SDK image_seed_scope ->captured UI callback; CLI t2i/i2i single-prompt --seed, MCP waited/queued and worker codec retain seed. | REST two-image 12042/12043 proof 29.44s; CLI seed 42 JPEG 1024×1024, 397,336 bytes. MCP/queued have offline parity, no independent live seed proof. |
| Image text/references | Durable REST jobs with owned local references | CLI/SDK/MCP image generation already exists; native named/entity/inline reference cross-product is not blanket integrated. | Image/upload/reference/native2K HTTP workflow 133.91s. Partial counts are explicit failures with preserved assets. |
| Video generation/count/frames/ingredients | REST uses CLI, serial count1–4 with checkpoints, image frames/references and model gates | CLI/SDK/MCP supported local-file modes exist; REST serial checkpoint behavior is its own wrapper. | Offline proof; paid live video generation not exercised. Seed/V2V/audio/extend/complete marker modes remain separate gaps. |
| System voice catalogs | Bundled default 30 plus explicit native catalog=google 30 | CLI character voices and MCP gflow_character_voices expose bundled constant. Dynamic native parser remains REST/private-worker integration. | Native/HTTP catalog proof. Custom voice CRUD and signed playback are unported. |
| CAPTCHA configuration/balance/stats | Protected ProviderKeys, masked REST configuration, loopback GUI balance; solver-generation REST guard 501 | Provider clients/native override are private image-worker preparation. Public SDK/CLI/MCP solver options are not provided. Do not import Unix-only fcntl-backed storage into portable SDK operations. | Actual CapSolver solved/submitted 1, accepted 0; Google unusual-activity403/gRPC7, no retry. Key/balance does not prove generation. |

## Reliability and caller invariants

The previous two-reference release gate is 5,098 passed/47 skipped, 90.56% coverage. Direct native mutations have ownership preflight, bounded post-create work and partial created identity on unknown outcomes; sequential SDK delete failures preserve completed identities separately from a later before-mutation refusal; they are not durable/idempotent REST jobs. No automatic generation or mutation retry is implied. Native operations share the normal profile lease. The current audit includes explicitly assigned browser proofs and spends no generation credits.

## Predict: UX and cross-platform review

CAUTION, confidence 8/10. Reuse one typed SDK/native service across REST, CLI and MCP, with explicit host dispatch and no requirement for REST SQLite registration. Existing `character create` generates portraits; preserve its defaults and introduce a clearly named create-from-images mode/command. Keep native IDs, copied-source semantics, project ownership, notes limits and partial-created-reference failures consistent in human/JSON/MCP responses.

Portable SDK methods must not import self-host server/admin/captcha storage: `selfhost/captcha.py` imports POSIX fcntl and uses a homelab secrets path. Prefer FlowApiClient plus pure native transports/services, existing profile lease and Path handling. Test Windows path quoting, spaces/Unicode, JSON serialization, normalized UUIDs and no-display errors. Queued mutation support requires durable accepted checkpoints and interrupted outcomes before exposing a queue mirror; existing image/video queue semantics alone do not prove safe CRUD replay.

Source-level gaps above are integration gaps, not claims of missing Google UI capability. Use the measured spike artifacts and [verification ledger](VERIFICATION.md), then prove new public caller paths live before calling them operational. Full endpoint contracts remain in [PARITY.md](PARITY.md).

## Expansion gates and live proof boundary

Adapter/legacy generated-portrait CLI regression, MCP schema parity and BDD
binding checks passed 77 tests. Native catalog adapters, local project wire
compatibility and existing MCP project regressions passed 52 tests; targeted
strict Pyright reports no errors. The previous full offline release gate is
5,098 passed / 47 skipped, 90.56% coverage; it does not validate the new expansion.

The first actual CLI/MCP run exposed a native notes-clear acknowledgement
mismatch; both owned fixtures were removed. After the measured native repair,
the full rerun passed **3 tests in 265.40 seconds**: CLI lifecycle, registered MCP
adapter lifecycle and CLI/MCP native inventory. Both character paths copied two
references, applied initial notes/Charon, listed/read them, cleared notes,
renamed/set new notes/Aoede, and removed the owned entity. Inventory matched
native project IDs across two disjoint pages and mixed image/video kinds, with
unknown completeness and no signed URLs. No generation or solver was invoked.
The strengthened SDK inventory proof is recorded separately in the ledger.
