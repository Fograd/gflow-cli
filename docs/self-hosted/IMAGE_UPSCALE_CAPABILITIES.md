# Fresh image upscale capabilities

This read extension reports current2K/4K download-menu availability for one exact native owned image. It opens the detail download menu without selecting a target, minting a token, generating, downloading or creating a job. Available items do not establish subscription entitlement, provider readiness or accepted upscale output.

SDK: `await client.get_image_upscale_capabilities(project_id=PROJECT_UUID, media_id=IMAGE_UUID)`.
CLI: `gflow image upscale-capabilities IMAGE_UUID --project PROJECT_UUID --profile NAME --json`.
Direct registered MCP: `gflow_get_image_upscale_capabilities(project, media_id, profile="default")`.
REST: authenticated `GET /v1/google-flow/images/upscale/capabilities?email=ACCOUNT_HANDLE&projectId=PROJECT_UUID&mediaGenerationId=IMAGE_UUID`.
REST defaults the project to the selected account's registered project. Project/media inputs are raw native UUIDs; no URL or inferred alias decoding is supported by this endpoint. Unknown/duplicate controls refuse before worker dispatch. Reads are synchronous; there is no queued worker/codec twin.

The SDK/CLI/MCP result contains `project_id`, `media_id`, `capabilities` and `scope`; CLI/MCP add `status="ok"`. REST uses `projectId`/`mediaGenerationId`, retains the same capability rows and sends Cache-Control:no-store.
Rows are ordered2k,4k and contain:
- `resolution`:2k or4k.
- `status`:available, disabled or unknown.
- `available`:true, false or null respectively.
- `reason`:stable observation reason, without UI/user text.

An actually observed enabled item returns available/enabled_menu_item; a disabled item returns disabled/disabled_menu_item. Missing, hidden, duplicate or unobserved items remain unknown. Unknown reasons include resolution_unobserved, resolution_ambiguous, menu_unobserved, menu_ambiguous, menu_context_unverified, download_trigger_unobserved, download_trigger_ambiguous, detail_context_unverified and observation_timeout.

Identifiers and strict fresh selected-project image ownership are verified before detail navigation. Invalid, foreign or non-image inputs refuse. Failure to establish ownership or read transport remains an error; UI uncertainty after ownership returns unknown. The read is bounded45seconds including page checkout, with bounded cleanup, and retains the normal profile lease. No URLs, captions, prompts, account emails, auth material or menu text are returned or persisted.

Observed availability is not cached authority. Paid image upscale still rereads its enabled-item guard before dispatch (and again after explicit-token mint), with existing2K/4K behavior. Discovery accepts either generated or uploaded owned images only where fresh native ownership verifies; absent UI support remains unknown.

A real intercepted Patchright BDD verifies enabled, disabled, missing, duplicate and menu-timeout behavior; unit coverage also verifies exact detail identity with zero target clicks, external calls, generation requests or token mints. Live account capability and accepted paid output are separate evidence. Pro plan names never establish Ultra or4K entitlement.
