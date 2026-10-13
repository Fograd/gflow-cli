# Nano Banana 2.1

Goal: explicitly select Nano Banana 2.1 through CLI, queued MCP and self-hosted REST.

Design: extend existing image model tables with BELUGA / nano2.1 and the measured
ten-reference ceiling. Preserve nano2=NARWHAL; prevent its picker match from
accepting 2.1. Fresh account metadata remains authoritative for availability and
lower reference limits. No transport, authentication, retry or schema changes.

Predict: GO with mitigations, confidence 9/10. Independent architecture, security,
performance, UX and minimality reviews agree on the existing route. All flagged
the old-name prefix collision; fix migrated, legacy and character matchers.
Do not infer generated-model identity from the requested name or a saved image.

Scope: ordinary text/image generation, batch intake, model catalogue, native slot
references and REST/MCP parity. Character generation gains no new model option.
Default migration is separate from additive support and waits for live proof.

## Tasks

- [x] Add failing alias, picker identity, reference, queue and REST regression tests.
- [x] Extend the existing model tables and public descriptions.
- [x] Add and run a read-only browser BDD against fresh account discovery.
- [x] Verify explicit CLI generation and a reference variation; at most two initial
  image submissions, no solver task, video or blind retry of uncertain acceptance.
- [x] Run the repository checks and independent review; document exact limitations.
- [x] Deploy after queue/SQLite checks, verify running source and authenticated API.

## Scenario coverage

| Risk | Expected result | Test |
|---|---|---|
| D3: 2 and 2.1 share a prefix | NARWHAL never matches BELUGA, including selected chip | unit/browser |
| D9/D11: new model or smaller account cap | BELUGA recognized; fresh cap can restrict ten | unit/browser |
| D11: eleven references | Reject before submission | unit |
| D13: queued MCP drops model | BELUGA and seed survive codec round trip | unit |
| D13: REST mapping missing | nano-banana-2.1 accepted; refs retain Auto policy | integration |
| D1/D2/D5: live refusal/uncertainty | Existing leases and refusal classification; no blind retry | live ledger |
| D6/D12: requested model differs | Record observed wire/output attribution separately | live ledger |

D4/D7/D8/D10 retain existing batching, error, path and headed-browser behavior;
no new concurrency, exception, platform or persistence mechanism is introduced.
Ten-reference metadata is not a claim of ten-reference visual fidelity.

## Live evidence, 13 October 2026

Read-only browser BDD passed on the original enabled account. Explicit CLI T2I
and I2I each sent exactly one native image submission; model field row[5] was
BELUGA, with zero and one reference respectively. Outputs decoded as JPEG,
1024×1024, 707432 and 667053 bytes. The edit changed blue glaze to coral while
preserving the teapot and scene. The reply itself does not expose model identity;
wire observation and selected UI model are retained separately from response data.
An initial profile-lock refusal occurred before browser acquisition/submission.
It was retried only after acquiring the lease. No solver, video or uncertain-write
retry was used. CLI and reference picker are live-proven; queued MCP model codec
is covered offline and deployed MCP catalogue will be read without another generation.

## Regression and review evidence

Independent code review found no actionable issues. Repo hygiene, doc links,
published-doc privacy and mirror checks, council-memory links, whole-tree Ruff
lint/format and Pyright passed. Duplication scan found no touched-code issue.
Full offline run: 8406 passed, five failed, five skipped; coverage 90%.
One failure was a broken local editable registration and passed after reinstall.
The other four reproduce on an isolated archive of unchanged base e8e75f63:
two excessive JSON nesting cases, legacy video CAPTCHA error ordering, and the
macOS synthetic browser session-restoration case. They are existing failures,
not a claim of an entirely green suite; unrelated production behavior is unchanged.

Surface review: CLI/direct MCP/queued codec preserve model identity; MCP help and
agent skill list 2.1; existing root command/index descriptions remain true; error
and exit-code contracts are unchanged; batch intake and dynamic model catalogue
include BELUGA while copied defaults remain unchanged; canonical and generated
docs agree. Character options deliberately retain their existing model choices.

Focused final regression: 203 passed, two unrelated platform/capability skips.
Production code commit 1829a5d8 deployed by fast-forward after both queues were
idle, both SQLite quick checks passed, and restricted database/config backups
completed. REST and MCP services restarted and remained active with exit status
zero. Production CLI models lists BELUGA / nano2.1 with a ten-reference ceiling.
Authenticated REST model reads returned HTTP 200 and BELUGA for both enabled
accounts; authenticated MCP tool discovery advertises nano2.1, and a fresh MCP
reference-model read returned BELUGA with ten effective references. No additional
generation was used for deployment verification. Defaults remain unchanged.
