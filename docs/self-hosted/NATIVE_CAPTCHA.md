# Supplied tokens on native generation adapters

Native reference video, Omni edit, extension, promotion and saved-TTS creation accept one
supplied CAPTCHA token. This is explicit interception support; Google acceptance
of external/provider tokens is surface-specific. Ordinary browser-owned minting
is unchanged when no override is supplied.

## SDK
Use the scoped helper around exactly one native operation:
```python
from gflow_cli.api.native_captcha import native_captcha_token
with native_captcha_token(token, project_id=project, action="VIDEO_GENERATION"):
    started = await client.extend_native_video(
        project_id=project, media_id=source, prompt="Continue", count=1
    )
```
Use AUDIO_GENERATION for saved-TTS creation. TokenMinter and the native audio
minter require the matching current https://flow.google.com/project/UUID page
and exact action before consuming. Tokens require20–20000 characters without
whitespace/NUL. Mismatch/reuse refuses without browser fallback. The scope resets
after success, failure or cancellation; children share one consumption state and
cannot use it after the parent exits. Independent scopes remain isolated.
One native batch submission may have multiple outputs; several independent
submissions require different scopes and fresh tokens.

## CLI and direct MCP
video reference-native, video edit-native, video extend-native and voice create
accept --captcha-token-file FILE. Use a private owned regular mode600 token
file; symlinks, oversized files and permissive modes refuse. CLI leaves the
user's file in place. The file contents never enter argv or normal output.

Direct registered MCP gflow_generate_native_reference_video,
gflow_edit_native_video, gflow_extend_native_video and gflow_create_saved_voice
accept optional captcha_token. This is confidential input; responses do not
echo it. There is no queued MCP twin for these native adapters.

## REST and private workers
POST /videos (native reference/edit), POST /videos/extend and POST /voices
accept captchaToken. It is mutually exclusive with captchaOrder/captchaRetry.
Validation occurs before queueing. The token goes into an atomic mode600 file
in the configured private captcha-input directory; durable job JSON contains
only its private file pointer. Workers permit only that configured directory,
read/unlink before installing the scope, and remove pending files on startup
failure or cancellation. No token is added to checkpoints, results or callbacks.
The same token is single-use and short-lived; queue delay may expire it.
An idempotent retrieval does not create another submission.

Provider selection and bounded refusal retries are supported on these dedicated
native workers. See [provider policy](CAPTCHA.md#dedicated-native-provider-controls).
This is explicit caller choice: default browser minting does not silently switch
to a paid solver. Only confirmed typed WAF refusal may trigger the next explicitly
requested attempt; accepted and unknown outcomes never replay. Provider-backed
Google acceptance evidence is surface-specific. Generic UI video and image-upscale token
paths remain distinct from these native adapters.

## Verification and troubleshooting
The free synthetic-video BDD passed1test,2warnings in35.73seconds. Actual native
R2V/edit SDK scopes consumed synthetic supplied tokens and reached pre-dispatch
checkpoints; the native audio minter used the matching AUDIO_GENERATION scope.
No generation RPC was submitted to Google. The synthetic video was archived
and original active media preserved. This proves interception, not CAPTCHA
acceptance or generated output.
Run tests/e2e/test_native_captcha_bdd.py with private profile/home/project and
GFLOW_CLI_E2E_NATIVE_CAPTCHA=1. Never send its synthetic tokens to Google.
A scope mismatch means the selected page/project/action disagrees; correct the
inputs rather than retrying that token. Expiry or a Google refusal does not
authorize automatic replay. See [CAPTCHA](CAPTCHA.md) for provider trial evidence.


## Native image2K/4K and generic video scopes
Image upscale --captcha-token-file and gflow_upscale_image(captcha_token=...)
use one IMAGE_GENERATION token bound to exact project/media/selected2K or4K.
Fresh same-page image ownership is required before a solver task. The scoped
token is consumed on the project homepage before opening the detail view; only
the exact correlated SPrCad request can use it. For4K, current enabled menu
availability is checked before mint and rechecked before dispatch.
The native_captcha_provider async SDK scope supports the same transport.
REST images/upscale accepts mutually exclusive captchaToken, configured
captchaOrder or captchaRetry1–10. Only confirmed single-RPC typed WAF refusals
without any accepted/unknown result may advance an explicit retry budget.

Generic video provider controls and portable/queued mirrors are documented in
[generic video CAPTCHA](GENERIC_VIDEO_CAPTCHA.md). Count1 is required. These
controls do not prove accepted external-token output or Ultra entitlement.

## Saved-voice and promotion CLI/direct MCP provider controls

The first public native provider mirror batch covers `voice create` and
`video upscale-native`. Both accept `--captcha-order CapSolver,2Captcha`
and `--captcha-retry 1..10`. The matching direct tools
`gflow_create_saved_voice` and `gflow_upscale_native_video` accept
`captcha_order` and strict-integer `captcha_retry`; both default to null.
The SDK service `services.native_voices.saved_voice_operation(operation="create", ...)`
accepts those controls and optional confidential `captcha_token`.

Omitting both controls preserves one browser-owned attempt. Explicitly setting
either selects configured external providers, even `captcha_retry=1`.
The number means total attempts, including the first. Provider order must contain
unique exact `CapSolver`/`2Captcha` names. Supplied tokens remain single use
and cannot be combined with either provider control; conflicts fail before token
file consumption or browser creation. Existing SDK supplied-token scopes also refuse
provider controls. Selected-provider setup/mint failures return a privacy-safe typed
configuration error with existing private-key configuration guidance.

These adapters reuse the existing native CAPTCHA policy and solver. Each retry
opens a fresh sequential client after the previous client teardown. Only an exact
negatively acknowledged typed WAF refusal permits another attempt. Accepted
preview/promotion work, uncertain saves/submission, cancellation and poll,
download or cleanup failures never replay. Existing ownership/model/target checks
still run before minting; enabling providers does not bypass them.

Keys use existing private provider configuration (`GFLOW_CAPSOLVER_KEY`,
`GFLOW_2CAPTCHA_KEY` or the configured private key store). No new environment
variables, credentials in command arguments, or durable queue token fields are
introduced. These native MCP tools remain direct; queued confidential tokens
remain refused. External solvers and the native operations may incur provider
charges/Google credits. This adapter batch has offline verification only and
does not establish Google generation acceptance.

Native reference/edit/extension and image-upscale CLI/direct MCP provider mirrors
are documented below. Their supplied-token behavior remains single use.
Generic image generation uses its separate `ImageOverrides` policy and is not
routed through the native token retry policy by this batch.

## Reference, edit, extension and image upscale CLI/direct MCP provider controls

`video reference-native`, `video edit-native`, `video extend-native` and
`image upscale` also accept `--captcha-order` and `--captcha-retry`.
Their direct MCP twins `gflow_generate_native_reference_video`,
`gflow_edit_native_video`, `gflow_extend_native_video` and
`gflow_upscale_image` accept optional `captcha_order` and strict-integer
`captcha_retry`. Omitted controls preserve one browser-owned attempt; explicit
retry, including 1, selects existing configured providers. Retry means 1–10
total attempts, not additional retries. Provider names are exact and unique.
Supplied tokens and provider controls are exclusive before file consumption or
client creation. Neither tokens nor provider keys enter durable job JSON.

The CLI reference/extension adapters forward nonsecret camel-case controls to
their existing workers. Edit, image upscale and direct MCP use the same existing
native policy around complete fresh-client callbacks; no second retry engine is
introduced. One direct MCP profile lock covers all attempts; video rate admission
occurs once. Only the existing exact negatively acknowledged WAF predicate may
permit another attempt. Accepted, uncertain, cancelled, partial, polling,
download and surfaced client teardown failures do not replay. A second teardown
failure following rejection stops selected-provider retries with a typed
configuration error. Existing model, ownership, checkpoint and menu preflight
remain in the SDK before minting. Disabled or unknown 4K capability never becomes
a CAPTCHA retry reason.

Explicit image providers require an actually loaded `flow.google.com` session
before the SDK is called. Unsupported or unidentified hosts refuse before minting;
settings alone do not prove the served host. Image uses IMAGE_GENERATION; video
uses VIDEO_GENERATION. Existing direct supplied-token compatibility remains
single use. The generic image generation `ImageOverrides` policy is separate.

This adapter batch is verified offline with synthetic tokens and clients. Live
provider/native acceptance for these four new CLI/MCP adapters was not run:
the parent release owns profile leases and paid allowances. The parent REST
image acceptance does not prove acceptance for native voice or video.
