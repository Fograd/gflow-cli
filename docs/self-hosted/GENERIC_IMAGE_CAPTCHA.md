# Generic image CLI and queued MCP CAPTCHA controls

Single-prompt `image t2i` and `image i2i` accept
`--captcha-order CapSolver,2Captcha` and `--captcha-retry 1..10`.
The registered `gflow_generate_image` tool accepts optional `captcha_order`
and strict-integer `captcha_retry`. Both default to null: omitting controls
uses the existing browser path once and installs no image provider override.
Explicit retry, even 1, selects existing configured providers. The number is
total attempts including the first; names must be exact and unique.

Explicit controls require an existing project UUID (`--project` or MCP
`project`), a loaded HTTPS `flow.google.com` session and the UI transport.
Legacy, unknown-host or experimental transport paths refuse before generation
or a solver task. Current model/reference/ownership/weighted-capacity preflight
remains in the SDK. Provider selection does not establish account entitlement.

```sh
gflow image t2i "A quiet harbour" --project PROJECT_UUID \
  --captcha-order CapSolver --captcha-retry 1 --json
gflow image i2i "Change the lighting" --ref IMAGE_UUID --project PROJECT_UUID \
  --captcha-order CapSolver,2Captcha --captcha-retry 2 --json
```

A single native request may produce 1–4 images. The override count and optional
seed match that request; seeded batches retain seed+index and existing returned
seed verification. CLI multi-prompt/file/stdin sources and manifest/batch paths
do not support these flags and refuse explicit controls instead of dropping them.
No generic image CLI token-file input is introduced by this batch.

## Queue, retry and recovery boundaries

`gflow_generate_image` uses the durable generation queue, including `wait=False`.
Only nonsecret `captchaOrder` and `captchaRetry` are serialized. Confidential
`captcha_token` requests refuse before queueing, even when no provider controls
are present. Codec validation independently rejects token values, token-file
aliases and private secret pointers; supplied-token support remains the existing
private REST path. No provider key or token enters a DTO, journal or queue payload.

The service and daemon reuse `run_with_image_captcha_policy` and
`ImageOverrides`; they do not use the native token policy or introduce a retry
engine. Each bounded sequential attempt has fresh one-use override state on
the same opened client, matching the existing REST image worker. The native
project/envelope and current trusted reload metadata/site-key/action must match
before minting. Only that override's exact submitted negative acknowledgment
permits another requested attempt. Raw 403, accepted, partial, unknown and
cancelled outcomes never trigger replay.

Generation alone is inside the policy callback. Attribution, downloads, history
writes and completion stay outside retries. Existing per-attempt submit and
remote-started queue checkpoints remain; interrupted submitted work becomes
indeterminate and never automatically reruns. Inspect existing media/workflow
handles and download journals before trying again. Provider setup/mint failures
return privacy-safe typed errors with existing key configuration guidance.

Provider keys use the existing private configuration and shared
`GFLOW_SELFHOST_ROOT` statistics directory. No new environment variables or
provider-default changes are introduced. Solver tasks and Google generation
may incur charges. This batch has offline synthetic CLI/MCP/queue/service
verification only; no live solve, generation or Google adapter acceptance was
performed. Parent REST acceptance evidence is surface-specific.

See [CAPTCHA policy and evidence](CAPTCHA.md) and
[native dedicated adapter controls](NATIVE_CAPTCHA.md).
