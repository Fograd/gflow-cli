# Owned opt-in CDP launch implementation plan

Goal: apply the useful launch experiment from upstream PR907 without its default-path, debugging-access or process-ownership regressions. User explicitly authorized fixing and applying PR907 on 5 October; PR882 is deferred.

Architecture: a shared `api/cdp_launch.py` launcher starts installed system Chrome on the existing profile under its existing lease and connects Patchright to that invocation's fresh loopback endpoint. `FlowApiClient` and the standalone image transport retain independent process ownership through every cleanup path. Existing generation request contracts, default flags, selectors, retries and dependencies remain unchanged. `GFLOW_CLI_CDP_LAUNCH` is false by default.

Predict verdict: CAUTION, five independent reviews completed. Architect 7/10, security 6/10, lifecycle 8/10, CLI/MCP compatibility 7/10, simpler alternatives 6/10. The following mitigations are implementation requirements. Browser startup is a hypothesis, not a proven cause of R12 native refusals.

|Risk|Required mitigation|
|---|---|
|Debugger exposure / endpoint substitution|Chrome allocates port zero; require fresh bounded regular `DevToolsActivePort`, exact browser endpoint and loopback binding; no wildcard allowed origins or attach-to-existing fallback|
|Orphaned authenticated browser|Retain owned process before any cancellable await; independent cancellation-complete reap before lease release; graceful shutdown first; forced cleanup is reported honestly|
|Wrong or damaged profile|Existing canonical profile below configured home, installed Chrome and channel compatibility; no cookie import/seeding, profile replacement or singleton-lock deletion|
|Silently lost launch policy|Apply viewport, locale and headers before application navigation and on new pages; refuse unsupported recording and launch kwargs before spawning|
|Unproven acceptance improvement|Run zero-generation comparison first; reserve at most the one remaining pro3 video attempt before retrying its previously refused promotion; no solver or hidden retries|

This reopens PLAN ADR13 only for an owned, opt-in launch experiment. The older 19/20 default baseline and R12's eight validated images/five clips remain evidence that normal startup can work. The four native video refusals justify investigation, not global replacement of the default launcher.

## Task 1 — Red regressions

- [x] Reproduce absent opt-in routing and define endpoint/process safety tests before implementation.
- [x] Cover unsupported engine/headless/channel/recording, profile escapes, stale or malformed endpoint, connect/setup failure, cancellation, forced/graceful/idempotent shutdown.
- [x] Cover both client and standalone image launch sites, unchanged default behavior, process exit before lease release and no cookie seeding.

## Task 2 — Minimal implementation

- [x] Shared owned launcher with strict configuration and endpoint checks.
- [x] Integrate typed false-default setting at both launch sites.
- [x] Independent cleanup across successful, partial and cancelled setup/teardown.

## Task 3 — Live comparison

- [x] Tagged zero-credit live BDD: original pro3 profile, ordinary/CDP startup, actual browser controls, original authentication, loopback debugger and confirmed cleanup.
- [x] Read fresh balances/models and inspect active jobs before any affected service restart.
- [x] Atomically reserve one remaining pro3 video slot only after prerequisites pass; one native promotion of retained V2 identity, no solver, no retries.
- [x] Retain exact refused V6c evidence: one `p0UkFb` submission, unusual activity/gRPC7, no output or solver. Acceptance remains unmet.

## Task 4 — Publication and delivery

- [x] Document option, requirements, incompatible recording, process environment and rollback; update generated mirrors.
- [x] Focused tests, required gates and independent review pass for published runtime:98 focused,8371 full,5 skipped,89.99% coverage; required80 threshold rechecked. Final harness/docs gate is recorded in the handoff.
- [x] Publish the tested code/docs aligned on all three authorized branches; deploy the same revision with idle queues and protected state/configuration preserved.
- [x] Update R12 handoff, final acceptance ledger and OVERNIGHT with actual results and remaining allowance. Global opt-in stays disabled unless live evidence supports changing it.

## BDD scenarios

Given an existing authorized original profile and the same installed Chrome,
when ordinary and opt-in startup each read the account without submitting generation,
then the expected original account and requested browser controls are preserved,
and every owned browser has exited before its lease is released.

Given opt-in startup requests an unsupported configuration,
when either deployed caller prepares its launch,
then it fails before spawning or submitting and the normal launch configuration is unchanged.

Given cancellation or a startup failure after owned Chrome starts,
when cleanup completes,
then the exact owned process is reaped before the lease is released and no unrelated browser is terminated.

## Follow-up evidence before the single paid retest

On 6 October, the final free BDD passed all four shared/standalone ordinary/CDP runs: fresh original pro3 identity and owned V2 video, 1010 credits unchanged, requested viewport/locale/header, webdriver false, loopback-only debugger, graceful Chrome shutdown and profile lease reacquisition. Cookie imports, generation and solver tasks were zero. Private evidence: `r12-pr907/free-startup-r8.json`.

Initial live failures exposed a migrated-auth legacy-cookie assumption, a missing standalone language header, and a Crashpad tracer retaining an exiting LXC child. An attempted crash-reporter-disable flag caused CDP attach timeouts and was removed. The final Linux launcher uses unique systemd ownership scopes, including Chrome's own exact fresh-PID desktop scope after independent process-group proof. It waits for natural browser exit before escalation and verifies the kernel control groups are empty. The retained failed-test process/tracer was cleaned only after exact ownership proof. No original fixture/profile was removed.

Focused checks: 98 passes. Earlier full run: 8,358 passes, five skips and one previously observed virtualized-picker DOM failure; it is not called all-green. The final quiet full run passed8371/5 skipped at89.99% coverage, with a separate required80 coverage check; independent lifecycle/compatibility reviews passed after blockers were repaired. PR907 head reviewed: `fa6547ac9f7e658bd953f372d54e076b52da7e0f`; no wholesale merge, dependency update, selector or retry change.

## Final single promotion result

V6c used the final pro3 video slot through deployed registered MCP with the owned CDP option enabled only in an invocation-owned runtime drop-in. Google explicitly refused `p0UkFb` with unusual activity/gRPC7; no output, solver task or observed credit decrease occurred. The pre-dispatch SDK field-name harness failure submitted nothing; its correction reused the same reservation. The durable response/checkpoint was inspected without replay. The runtime drop-in and derived600-mode token fixture were removed; ordinary startup is restored. Both R12 video allowances are exhausted. The option is applied and startup-validated on CC Linux, but an acceptance improvement is unproved. PR882 remains deferred. Final branch/deployed SHA and final gates are recorded in root R12 handoff.
