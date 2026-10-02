# Seeded images

The REST image endpoint adds seed enforcement through the current migrated
`ogiZ0b` submit. It changes Google's actual per-output seed field, not merely
response metadata. Project, count and envelope structure are validated before
Google submission. Returned Google image records must confirm the exact seeds.

A request with `seed: N` and `count: C` uses the deterministic sequence
`N, N+1, ... N+C-1`. The supported range is `0` through
`2147483647-C+1`; booleans, negative and out-of-range values are invalid.
The sequence is this fork's explicit batching convention. It does not assert
that useapi uses the same convention for multiple outputs.

Seed control currently applies only to REST image generation. The upstream CLI
and image MCP signatures have not gained seed options. Video seed transport
still needs observation and remains explicitly unsupported by this adapter.
A seed helps reproduce a request; it does not promise byte-identical output
across model versions or changing references.

The wire field was observed on2026-10-02 in a request aborted before reaching
Google. Offline tests check exact slot changes, preserved fields, wrong project,
wrong count and one-shot submission. Live evidence is recorded in
[VERIFICATION.md](VERIFICATION.md); absence of a successful live row means it is
still unverified in the deployed service.
