# Native page-owned RPC execution context

Cause proven before this change: default Patchright page.evaluate uses an isolated
world where window.WIZ_global_data is undefined. Root's bounded pro3 override of
only WIZ expressions with isolated_context=False returned 13 native model usages,
minimum 4 credits, with zero generation. No engine default change is proposed.

Use the issue-resolve Bug Lane: source audit → root scenarios → failing offline
regressions → smallest shared engine-aware kwargs → affected-surface verification.
The existing mint_evaluate_kwargs already encodes this engine distinction for
page-owned grecaptcha. Reuse that policy with a page-owned name, retaining its
mint compatibility wrapper. Do not globally patch evaluate or generic DOM reads.

Scenarios: Patchright WIZ RPC/model reads, submit and poll calls must use main
world; Playwright must receive no unsupported keyword. Native TTS grecaptcha and
WIZ calls share the policy. Native archive WIZ fetch is included. Readiness waits
remain unchanged: Patchright wait_for_function has no isolated_context argument.
Cancellation, preassigned checkpoints, one-submit/unknown outcomes and all
ownership validation stay unchanged. Never log session fields, tokens or URLs.

Offline validation covers both engines and all affected expression categories.
Root owns free actual native reads and paid acceptance; mocked tests do not
establish browser or rendered acceptance. No paid or browser calls in this slice.

Verification: baseline engine-parameterized regressions produced nine expected
Patchright failures and nine Playwright passes before source edits. Final focused
native/context/engine/CAPTCHA/voice suite passed 124 tests. New opt-in actual-page
BDD is authored with a generation/mutation RPC guard but was not run by this
agent. Root must execute that free affected-surface acceptance on the explicit
private profile/project before any paid acceptance claim.

Targeted Ruff and Pyright passed (zero type errors); git diff --check passed.
The opt-in BDD skipped without explicit credentials, as intended.

Coordinator live affected-surface result: pro3 BDD exited0 with zero generations.
This verifies the actual page-owned model-read context; paid rendering remains
separate. Final frozen-source checks passed, including6484offline tests with89%coverage.

Actual REST alias acceptance:2tests passed in61.34seconds using the sandbox current
source and real private worker. Image/video aliases were registered/read/removed
without generation or Google mutation; raw-UUID fresh read survived alias cleanup.
Pro3 fresh character fixture create/read from a verified existing image passed
without image generation. A one-output four-credit abra_r2v_4s_360p
character+preset trial was explicitly WAF-rejected, unknown=false, accepted0.
Campaign reservations: pro1 images1/videos0; pro2 images0/videos1; pro3
images1/videos1. Rendered acceptance remains open; final frozen-source gates passed.

The paired R02 adapter adds explicit immutable HTTP alias bindings, fresh verified
account/project/media/type checks, and local-only removal. Unknown aliases never
strip a UUID suffix. Council ownership/privacy review returned GO. SDK/CLI/MCP
continue taking raw UUIDs, with no new queued tool or provider identity decoder.
Image/video registration/read/removal BDD passed against a real worker.

D0 gate: hygiene, links, public PII, generated mirrors, council references, Ruff,
formatting and strict src Pyright passed. Full suite:6484passed,5skipped,89%coverage
in207.28seconds. Publication/deployment follows the idle queue gate.
