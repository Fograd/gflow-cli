# Supplied tokens on native generation adapters

Native reference video, Omni edit, extension and saved-TTS creation accept one
supplied CAPTCHA token. This is explicit interception support; Google acceptance
of external/provider tokens remains unverified. Ordinary browser-owned minting
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

Provider selection/retry controls are validated but remain HTTP501 until Google
accepts a controlled provider-backed request. No automatic replay follows an
unknown write or rejection. Image generation retains its separately measured
request-rewrite hook. UI text/frame video, image upscale and CAPTCHA-free video
exports are outside this native batch; unsupported controls remain explicit
refusals and are tracked in R06/R07.

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
