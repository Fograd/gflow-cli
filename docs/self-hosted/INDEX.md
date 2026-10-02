# Self-hosted fork documentation

This fork adds an HTTP API and native image/video export adapters to upstream gflow-cli. Complete useapi compatibility is still a tracked goal, not a claim about this build.

| Guide | Purpose |
|---|---|
| [Setup and operation](OPERATIONS.md) | Install, headed Chrome, three separate account logins, systemd, credentials, recovery and backups |
| [API guide](API.md) | Configuration, supported requests, examples, jobs, callbacks and error contracts |
| [Compatibility inventory](PARITY.md) | Every useapi Google Flow endpoint, parameter gaps, native/local differences and next work |
| [Native seed controls](SEEDS.md) | Exact payload control and verification limits |
| [Private CapSolver key editor](CAPSOLVER_GUI.md) | Save/remove a key and check balance through SSH; no paid tasks |
| [CAPTCHA configuration](CAPTCHA.md) | Private provider keys, supplied tokens, image-only limits and evidence |
| [Migration guide](MIGRATION.md) | Tee pipeline integration, opaque references, verification, cutover and rollback |
| [Local concatenation](CONCATENATE.md) | Local FFmpeg behaviour, trim rules, quality and security boundaries |
| [Bounded reliability test](STRESS_TEST.md) | Ten-image pilot, partial-batch finding and CAPTCHA evidence limits |
| [Verification ledger](VERIFICATION.md) | What was actually tested live/offline and which profiles/features remain unverified |
| [Deployment sample](../../deploy/selfhost/README.md) | Service unit and operator environment file layout |

For upstream CLI/MCP features, see [the upstream documentation index](../INDEX.md). Runtime capability discovery and OpenAPI are authenticated; API availability does not imply that every Google operation has been live verified.
