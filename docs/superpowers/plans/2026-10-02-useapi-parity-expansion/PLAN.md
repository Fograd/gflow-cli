# Useapi parity expansion

Goal: finish the remaining self-hosted Google Flow operations and document each contract, operational difference and verification status in this fork.

Predict: CAUTION, 8/10. Independent architecture, security, performance, UX and simplification review requires owned references, profile leases, checkpointed outputs and observed RPC schemas. No capability is inferred from host membership. User already authorised autonomous execution.

## Tasks
- [x] Add existing CLI video start/end-frame and image-reference modes, resolution and count handling with per-output checkpoints.
- [x] Add bounded synchronous responses, asynchronous jobs and documented list filters without duplicate submissions.
- [x] Add account registration/unregistration for existing local profiles and safe local asset maintenance; do not import passwords or claim cookie presence proves Flow access.
- [ ] Measure missing native project/media, character, voice, seed and video extension surfaces; implement only with observed contracts.
- [ ] Add CapSolver/2Captcha integration with private key storage, bounded solves, masked configuration and accurate statistics; prove actual token consumption before calling it supported.
- [x] Update API guide, compatibility inventory, deployment and migration instructions, examples and verification ledger.
- [x] Run targeted, live zero-credit and repository gates; independently review; deploy and publish to the fork.
  Gates: final4969passed/47skipped/90.36%; native resourceBDD1pass, seedBDD1pass; lint/types/docs/securityreviewgreen. Deployed with no activejobs. Published expansion68569e4b to the fork develop and feature/self-hosted-flow-api branches.

## Completion criteria
Every remaining option has either an implemented tested path or an evidence-backed blocker with reproduction and next work recorded. This criterion documents progress; it does not imply complete useapi parity when blocked operations remain.

## Current evidence and remaining work

Image seeds and native MP4 upload/timeline/archive passed real-profile BDD. Provider configuration, bounded clients and stats are implemented, but provider generation is guarded501: earlier main-world hooks failed, then native reload probes measured action metadata; actual replacement acceptance remains unproven. Supplied-token rewriting is covered offline; live replacement acceptance remains unverified. Character/saved-voice investigation and global catalogue/extension/promotion contracts remain in the parity inventory with measured next probes. These unchecked native features prevent claiming complete useapi parity.


## Private CapSolver key editor follow-up

Predict simplification review: CAUTION/GO. A tiny loopback-only FastAPI editor on127.0.0.1:8845, opened in Vivaldi through SSH forwarding, avoids storing the REST bearer in the browser. Reuse ProviderKeys and existing httpx; do not add a session framework or dependencies.

Before publication verify exact Host/Origin, process/page CSRF header validation, nonce CSP, no-store and frame DENY; no key interpolation into HTML, query actions or credential logging. Only CapSolver save/remove/masked status and bounded read-only balance are in scope. Balance uses a15second deadline and64KiB streamed cap, with no paid tasks. Test foreign Origin/Host, missing CSRF, stored key masking, failed provider replies and timeout. Keep actual third-party replacement acceptance explicitly unverified; a working key editor or positive balance does not make image solving operational.

## Latest stable publication gate

5,085 passed / 47 skipped, 90.44% coverage in 223.54 seconds; Ruff checked 570 files clean, strict Pyright reported zero errors. Hygiene/docs/privacy/website/council and staged private-identifier/real-key scans passed. Native HTTP catalog BDD: 1 passed in 33.03 seconds and character CRUD BDD: 1 passed in 91.94 seconds cover documented narrow flows. Actual CapSolver trial solved/submitted once but Google rejected; public provider HTTP 501 guard remains. No complete parity claim. Second-image reference work is a separate spike held outside this verified publication snapshot.

## Second-reference completion

- [x] Measured native portrait/body slots and two-reference copy; both originals preserved.
- [x] Verified adapter BDD: 1 passed in 34.11 seconds; deployed HTTP lifecycle BDD: 1 passed in 97.82 seconds; owned test entity cleaned up.
- [x] Validated both registered image bytes/account/project and active native workflows before entity creation; retained shared 45 second post-create deadline and partial identity.
- [x] Ran stable offline gate: 5,098 passed, 47 skipped, 15 warnings; 90.56% coverage in 219.93 seconds. Strict Pyright zero errors; Ruff 571 files clean; no new duplication findings.
- [x] Updated API/operations/parity/evidence guides and reviewed the implemented scope. Six-axis CLI checks not applicable: REST/worker-only extension.
- [x] Staged hygiene checked 1,310 files; staged real-key/private-identifier scan clean. Published second-reference snapshot acd0d69b15 to both develop and feature/self-hosted-flow-api; remote GitHub heads verified.

Voice assignment, custom voices, generation grounding and remaining video controls are still tracked gaps; two-reference support does not imply full useapi parity.
