# Native asset lookup scenarios

| Dimension | Scenario and required evidence |
| --- | --- |
| D1 auth | Explicit selected profile; expiry fails read without scanning accounts. |
| D2 WAF | No solver/token mint or generation fallback; transient read failure remains read failure. |
| D3 surface | Exact current as29s codec, no captions/selectors for identity. |
| D4 resume | No mutation/replay; downloads atomic and do not overwrite unrelated files. |
| D5 concurrency | Concurrency one completes; deadline includes checkout; release once on cancellation. |
| D6 data | No fabricated Store/catalog ownership; signed URLs never persisted. |
| D7 platform | Path handling portable; contained REST outputs, no caller-selected server paths. |
| D8 mirror | SDK, CLI, synchronous direct MCP and REST maintain native scope/options; durable URL queues are not applicable to GET reads. |
| D9 input | Invalid IDs/type/project rejected before lookup; ambiguous unions/frames fail. |
| D10 content | Thumbnails/transcodes never silently replace media originals. |
| D11 privacy | URL not in errors/logs/history; credentials/ports/redirect hosts rejected. |
| D12 failure | Missing row in incomplete snapshot says unresolved, not deleted. |
| D13 evidence | Zero-submit live image/video lookup/download BDD; generated and uploaded arms covered. |

Critical tests: transposed identity, wrong project/workflow, duplicate frame,
ambiguous union, audio/character rejection, untrusted URL and redirect, byte/MIME
mismatch, cancellation cleanup. High tests: generated/uploaded fields, missing
original URL, zero-byte/oversize responses, timeout, native REST explicit account,
direct read option parity. Archived metadata may resolve; no automatic restore.

BDD: Given an explicitly selected logged-in account and owned image/video in a
fresh project snapshot, when lookup reads exact current metadata and downloads
its typed media, then identities and decoded content match and no generation,
upload, restore or deletion request was dispatched.
