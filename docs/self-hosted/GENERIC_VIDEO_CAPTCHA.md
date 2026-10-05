# Generic video provider controls

The ordinary text/image/ingredient video composer supports explicit supplied
tokens or configured CapSolver/2Captcha providers at count1–4. It validates a fresh
same-project UI envelope, matching VIDEO_GENERATION reload metadata and the
trusted current site key before calling a solver. Provider selection is optional;
saving a key alone does not enable paid solving.

## Interfaces

HTTP `POST /v1/google-flow/videos` accepts exactly one of `captchaToken`,
`captchaOrder` or `captchaRetry`. `captchaToken` is one use.
`captchaOrder` is a comma-separated unique configured provider order, such as
`CapSolver,2Captcha`; fallback happens only before Google submission if solving
fails. `captchaRetry` is an explicit integer1–10 attempt budget. Count2–4 uses one exact native request and retains every actual output. Native reference/edit/extension adapters have separate batch contracts. See [batch results](VIDEO_BATCH.md).

CLI `gflow video t2v`, `i2v` and `r2v` add `--captcha-order`,
`--captcha-retry 1..10` and `--captcha-token-file FILE`. Supply an explicit
`--project UUID` and count1–4. Token files must be private owned regular mode600;
the CLI does not delete the user's file. Tokens never enter argv or normal output.

SDK:

```python
from gflow_cli.services.video_captcha import generate_video_with_captcha

result = await generate_video_with_captcha(
    client, req=request, project_id=project,
    captcha_order="CapSolver", captcha_retry=1,
)
```

For count2–4 the wrapper dispatches generate_videos_batch and returns VideoBatchResult; singular count1 keeps generate_video. One shared CAPTCHA context/token serves the complete exact request vector. Every row is validated before solving.

The wrapper also accepts confidential `captcha_token` and the ordinary
`generate_video` output, download, poll and callback keyword arguments. Supplied
tokens force one attempt and cannot be combined with provider order or retry
controls, including captcha_retry=1 and an inherited native supplied scope. Provider order/retry can be combined on the portable
wrapper/CLI/MCP surfaces; HTTP preserves the vendor's mutually exclusive controls.

Registered MCP `gflow_generate_video` accepts `captcha_order` and
`captcha_retry` for both wait modes. Its durable queue contains only these
non-secret controls. `captcha_token` explicitly refuses before enqueueing until
a confidential queued-token lifecycle exists. Native direct MCP tools have their
own confidential single-use token interfaces.

## Retry and outcome rules

A new attempt is permitted only after one exactly correlated dispatched RPC
positively reports the typed unusual-activity WAF refusal, with no accepted or
known output handles. Each attempt uses fresh UI/body/request IDs/token and scope.
Successful solver completion is separate from Google submission and acceptance.

Mixed/duplicate/masked acknowledgements, any known remote handles, malformed
responses, content/auth/entitlement errors, timeouts, cancellation, accepted
poll/download/save failures and late callbacks never replay. Queued jobs and
callbacks retain unknown outcomes for inspection. Supplied tokens are never
retried. Solver latency does not renew scope or permit a different project.

Missing selected provider keys or solver failures return a privacy-safe typed
ConfigurationError with private key configuration guidance.

Provider-backed accepted rendering still requires a live R12 proof. The actual
pre-dispatch generic video body/reload capture passed with zero requests forwarded;
that evidence establishes the integration contract, not Google acceptance.
