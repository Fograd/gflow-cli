# JSON and text form requests

The eighteen mapped mutation routes declared in authenticated OpenAPI also accept multipart/form-data text fields.
Raw `/assets` uploads retain their PNG/JPEG/WebP/MP4 byte contract.

Each form field appears once and has no filename. `prompt`, `model`, `email`,
references, cookie tables and provider tokens stay literal text. Numeric controls
such as `count`, `seed`, `duration`, `captchaRetry`, `startFrameIndex_1` and `endFrameIndex_1` use JSON numbers. Booleans
such as `async`, `enabled`, `verified` and `localOnly` use exactly `true` or `false`. `media`
and `mediaGenerationIds` use JSON arrays. These conversions feed the existing
route validation and selected-account ownership checks.

```python
response = client.post(
    "/images",
    files={
        "prompt": (None, "A blue circle on white"),
        "count": (None, "1"),
        "async": (None, "true"),
    },
)
```

The client supplies the same bearer authorization and optional idempotency header
as a JSON request. Form parsing does not create a second job type or alter
polling/callback semantics. Supplied CAPTCHA tokens follow the same private
one-use path; they do not enter public responses or durable request payloads.

Duplicate fields, file parts, malformed boundaries, nested MIME parts,
content-transfer encodings, non-UTF-8 text and invalid typed values refuse422
before queue creation. At most64 unique text fields are accepted. Existing
request body limits apply: normal mutations64KiB and cookie account import2MiB.
The parser also bounds each text part and total form body to2MiB. Raw asset
uploads retain their20MiB limit. Errors do not echo the form body.

This is HTTP transport compatibility. SDK, CLI and MCP retain their existing
typed controls and do not send MIME bodies.

Authenticated OpenAPI advertises both JSON objects and multipart text objects for every mapped form route, including DELETE assets. Fork extension routes keep their separately documented contracts. Duplicate/malformed MIME header parameters and excessive nested JSON refuse422 without body echo.
