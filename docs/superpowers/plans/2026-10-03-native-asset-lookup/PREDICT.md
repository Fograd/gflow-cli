# Native asset lookup prediction

Proposal: advance roadmap R02 with fresh, selected-account/project native image and
video metadata, protected media URLs and bounded downloads, mirrored through SDK,
CLI, synchronous direct MCP and REST; generation queue mirrors stay separate. Character/audio details remain separate typed
capabilities; composite useAPI handles require verified translation.

Architect GO 8/10 and Security CAUTION 7/10 independently reviewed by
lookup_arch_security. Performance CAUTION 8/10 and CLI/MCP UX CAUTION 8/10
independently reviewed by lookup_perf_ux. Root Devil's Advocate CAUTION 8/10:
reuse native snapshot/RPC boundaries, avoid generic ownership registry, and prove
URL semantics before download wiring. A URL with a plausible path alone does not
prove original media. Current existing metadata order is not generation order.

Convergence: CAUTION, proceed with constraints. One fresh snapshot and one page
checkout; exact project/media/workflow and exclusive kind proof; strict single RPC
response; overall deadlines; cancellation cleanup. No account scan, synthetic
Store asset, generation fallback, mutation, solver call or generation decoder
change. Signed URLs are bearer credentials, output only by explicit request,
excluded from routine logs/queues/history. Download hosts, ports, redirects,
actual content, bytes and paths must be constrained. Missing partial inventory is
not proof of permanent absence. Mirror defaults/options/response/error semantics,
including useAPI video-only raw and invalid supplied raw=false behavior.
