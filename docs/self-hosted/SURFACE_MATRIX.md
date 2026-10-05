# Current public surface audit

This is the 4October2026 implementation audit. The release revision and actual
live results are recorded in [verification](VERIFICATION.md). Supported adapters,
accepted rendering and vendor compatibility differences are separate columns.

| Feature | SDK / CLI / MCP | Self-hosted REST | Proof or remaining boundary |
|---|---|---|---|
| Character CRUD | Shared native create-from-images/list/detail/update/delete; direct MCP confirms removal | Native owned image/entity metadata and exact registered aliases | Earlier actual CLI/MCP/REST CRUD accepted; rendered grounding remainsR12 |
| Project/media/history | Bounded native projects, attached/timeline/history pages, explicit resume | Native defaults, summaries, URL-free observations and durable sync | Live disjoint pages/resume passed; completeness remainsunknown |
| Account characters/saved voices | list_account_resources, project account-resources, direct MCP continuation | assets/resources/{email}, opaque kind/project/principal-scoped continuation | Actual corrected SDK plus resume passed; deployed correction/readproof recorded separately |
| Native media lookup | Fresh owned typed image/video/audio/character/voice detail | Exact registered composite mappings and fresh URLs | Image/video/character reads accepted; generic audio ismetadata-only; arbitrary vendor decoding unsupported |
| Image/MP4 upload | Native upload mirrors and explicit MP4 rights consent | Raw PNG/JPEG/WebP/MP4,20MiB; WebP validated/converted | Own fixture upload/read/delete proofs; no implicit global consent |
| Image references/Auto/seed | Ordered local/native/character inputs; first ordered local/native image Auto policy; existing image seed scope | Same owned bindings/privateworker and request count validation | Accepted ordered Lite ten-reference SDK output reused; fresh reference preflight and controlled worker forwarding; per-reference influence remains R12 |
| Image upscale | Shared native2K/4K export; optional controlled override/token scopes |2K/4K fresh entitlement-before-mint and explicit WAF-only retries | Earlier2K accepted; latest pro1 provider2K traffic-refused; Pro4K entitlement remains unavailable |
| Generic video | Singular count1; generate_videos_batch count2–4; CLI all outputs; queued MCP all handles/files | One native request/job; all-output checkpoint/recovery | Real count4 request/4IDs aborted beforeforwarding; accepted plural rendering requires extra allowance |
| Native reference/edit/extend | Canonical positional image/entity/audio and fresh exact model/budget guards; direct MCP | Private native workers, supplied/provider controls and original slot mapping | Free ownership/binding/request proof; accepted output remainsR12 |
| Video promotion/exports | Native720/1080/4K promotion and export/GIF; current model/entitlement guards |1080default, exact source requirement, download/GIF/concat adapters | Existing read/preflight proof; accepted promotion/entitled4K remainsR12 |
| Saved/system voices | Native presets, saved TTS CRUD/detail/playback, metadata binding and direct MCP | Combined system/user catalog and strict resource aliases | Real audio previews WAF-refused, credits unchanged; accepted lifecycle pending |
| Delete/archive |1–100 canonical distinct IDs, ordered duplicate normalization, exact owned receipts/NOT_FOUND, whole-batch archive and known/pending recovery | Exact registered alias/UUID normalization, zero-write repeats, present-only mixed writes; local cache and alias removal separate | Invocation-owned fixture/receipt proof; arbitrary missing IDs do not imply success |
| Providers/tokens | Explicit SDK/CLI/private-file/direct native token scopes; queued generic MCP order/retry | Private provider editor, one-use input files, generic count1–4/native/image policies | Solving/forwarding observed; Google acceptance unproved; confidential queued MCP tokens refuse |
| CAPTCHA stats | Observer telemetry shared by workers; no provider key outputs | Local phase events/filtering and matched observer elapsed averages | Legacy migration/noinventedtiming tested; vendor-wide anonymized data unavailable |
| Accounts/sessions | Private separate profiles, fresh identity checks, secure session retention | Staged expected-principal/project verification, atomic accepted-refresh lineage | Latest import/identity proof blocked; human renewal required where expired |
| Scheduler/jobs | Existing score/queue ordering, all-output SDK/MCP checkpoints | Local typed quota/model cooldown policy, flat429, sync/async/callback/idempotency | Offline refusal/recovery policy tests; local cooldowns are not Google reset predictions |
| Request contracts | Existing typed SDK/CLI/MCP controls | JSON and multipart text for all18 mapped mutations, authenticated OpenAPI | Duplicate/header/deepJSON/file refusal beforequeue; raw uploads unchanged |

The MCP server currently registers43tools. Native direct mutation tools have no
queued twin unless explicitly documented. Queued generic/image jobs and REST
private workers retain different process boundaries, so final E2E covers each.

See [API](API.md), [roadmap](PARITY.md#roadmap), [contract audit](CONTRACT_AUDIT.md),
[batch results](VIDEO_BATCH.md), [scheduler](ACCOUNT_SCHEDULER.md),
[forms](FORM_REQUESTS.md) and [final E2E](FINAL_E2E.md).


R04 closure, 5 October: supported reference implementation is complete. Native
R2V/V2V share strict active audio ownership and unique current capacity pools;
model reads include max_characters. CLI --reference-slot and direct MCP
reference_slot_ids mirror existing SDK/REST positional maps, with holes/mixed slots
retained. Existing saved-audio final codecs passed live before minting; previous
character/system-preset evidence is reused. No current unsaved uploaded-audio
cohort was available, so that live shape coverage remains an evidence limitation.
Rendered video/speech and semantic grounding remain R12, with no acceptance claim.
