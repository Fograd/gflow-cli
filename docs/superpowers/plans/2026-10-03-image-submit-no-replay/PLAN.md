# Browser image submission safety

Bug Lane: image generation entered the client's generic HTTP retry loop even
when its transport clicked the browser's Generate control. A transport timeout
after Google accepted the request could repeat a billed action. Diagnosis:
the browser transport owns submission and must classify dispatch uncertainty;
a NetworkError retry predicate does not prove an action was refused.

Predict aggregate CAUTION8. Architecture: keep dispatch evidence in transport,
not HTTP server concerns in SDK. Security: never reveal wire tokens; safe UUID
handles only. Performance: one approved route guard observes every image and
marks uncertainty before awaiting continue. UX: typed exit40 with inspect-first
remediation, cancellation stays cancellation. Devil: preserve non-browser HTTP
retry behavior and explicit pre-dispatch refusals.

- [x] Red tests for native and labs page-owned transports entering retry factory;
  non-browser HTTP transport retains existing retry behavior.
- [x] SDK submits once for page-owned image transports.
- [x] Native route marks possible dispatch before continue and tracks known UUIDs;
  approved dispatch followed by timeout/HTTP500/DTO failure is nonretryable.
- [x] Cancellation remains CancelledError with safe internal uncertainty context.
- [x] Definite guard refusals remain pre-dispatch refusals.
- [x] Literal canonical prompts without references avoid unnecessary ownership reads.
- [x] Real native image BDD after session restoration, separate from fault mocks.
- [x] Whole-tree checks, independent review and documentation.
- [x] Publish and deploy the frozen verified checkpoint.

Offline fault tests validate our lifecycle and do not prove Google availability.
Known handle recovery does not automatically regenerate missing outputs.


Live proof: one SDK image BDD passed in 104.75 seconds after manual session
restoration. Exactly one native request passed the correlated positional guard
and was dispatched. The result decoded as a 1024×1024 JPEG (270277 bytes),
with private remote handles checkpointed before download. The owned temporary
character was deleted. No generation or solver retry occurred.

Native observer safety review: dispatch is marked before awaiting route continuation,
so loss of its acknowledgement cannot restore retry eligibility. Parsed media/workflow
UUID handles are saved before DTO construction; a DTO failure reports those safe
handles in the typed unknown outcome. Post-dispatch timeout, malformed response, or
ambiguous server failure is nonretryable. Definitive WAF/policy refusal keeps its own
typed classification, but the page-owned SDK still submits only once. Guard-aborted
requests that never dispatched retain pre-submit refusal semantics.

Cancellation propagates asyncio.CancelledError; its safe internal uncertainty context
is attached only if submission may have occurred. It does not become a normal success
or retryable error. Only bounded valid UUID handles are retained; tokens, wire payloads,
URLs, and local paths are excluded. These cancellation/fault paths are tested offline;
the successful live proof does not simulate or establish Google's billing on faults.

Independent review exposed one additional recovery defect: a post-dispatch page navigation or closed-page URL read could lose the pinned project or mask submission uncertainty. Both native callers now pass the validated project; the observer snapshots it before dispatch and uses it for guard and recovery. Six red-to-green navigation/closed-page DTO/timeout/cancellation cases preserve project and known handles. Focused composer/positional/entity suite: 157 passed in 28.48s; Ruff and strict Pyright clean. No browser or generation was used for these fault regressions.

Frozen-source full regression: 5495 passed, 28 skipped, 15 warnings, 90.62% coverage in 238.49s. Whole-tree Ruff/strict Pyright and documentation/privacy/mirror gates passed.

Published/deployed fd56b2e6. Production queued health and registered MCP protocol passed; no generation in that deployment smoke.
