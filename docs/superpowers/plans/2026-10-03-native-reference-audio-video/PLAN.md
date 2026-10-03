# Native reference video with audio ingredients

The user requests all useapi controls, prioritizing implementation and placing live E2E at the end. This increment implements actual image/audio ingredient requests from the publicly deployed Flow frontend. No browser or paid generation is part of the offline implementation.

## Predict and scenarios

Security: require fresh owned project/media/workflow triples with exclusive image or audio union arms; no caller type hints, signed URLs or provider secrets in public errors. Validate absolute budgets before checkout and intersect fresh tier/model requirements and budgets before mutation. Assign output identifiers and call the checkpoint before one dispatch. Unknown acknowledgments retain safe paired IDs and never trigger generation replay.

Performance: one project snapshot and one model/tier read per invocation; count capped at four, input budgets at seven images/five audio. Poll only assigned output handles; five-second bounded polling. No inventory-difference discovery or per-waiter generation.

Scenarios: positional image/audio markers and literal unknown names; audio-only ingredients; missing reserved slots; unrelated or multi-arm assets; unavailable model or excessive model-specific budget; checkpoint before dispatch; dispatch timeout or NULL acknowledgment; polling unrelated identity; CLI exit40 and worker pre-browser validation.

## Implementation and evidence

The deployed project frontend bundle SHA256 is `fde0520503cde337170e1314e9904b1da4e279d0fea2f10df7cb417ac448d31b`. Q4a/U4a uses MZZa6b (`BatchAsyncGenerateVideoReferenceImages`): prompt1, images2, native key3, aspect4, metadata6, audio8, resolution12. Image refs use media field2; audio refs use name field1. Prompt WI reference2 contains VI media1/audio2, both name1/handle2. Numeric video seed is not inferred from skipped fields or assignment UUID seeds.

SDK, CLI and the private worker use this codec. Parent integrates HTTP/MCP separately. Focused codec/ownership/unknown/CLI tests pass; generation acceptance and actual downloaded-video proof remain deferred to final E2E. No claim that source-schema tests prove Google acceptance.
