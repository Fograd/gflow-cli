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
- [ ] Run targeted, live zero-credit and repository gates; independently review; deploy and publish to the fork.
  Gates: final4969passed/47skipped/90.36%; native resourceBDD1pass, seedBDD1pass; lint/types/docs/securityreviewgreen. Deployed with no activejobs. Publication pending.

## Completion criteria
Every remaining option has either an implemented tested path or an evidence-backed blocker with reproduction and next work recorded. This criterion documents progress; it does not imply complete useapi parity when blocked operations remain.

## Current evidence and remaining work

Image seeds and native MP4 upload/timeline/archive passed real-profile BDD. Provider configuration, bounded clients and stats are implemented, but provider generation is guarded501: native action metadata was not captured by main-world or early execution hooks. Supplied-token rewriting is covered offline; live replacement acceptance remains unverified. Character/saved-voice investigation and global catalogue/extension/promotion contracts remain in the parity inventory with measured next probes. These unchecked native features prevent claiming complete useapi parity.
