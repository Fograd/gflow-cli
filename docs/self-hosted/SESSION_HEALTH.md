# Session health and profile preservation

A valid Google sign-in or stored cookie does not guarantee access to the Flow
editor. Flow can require an additional human identity check and send the browser
to its public `/about` page. The project has a measured precedent in
[known issues](../../KNOWN_ISSUES.md). It does not establish the cause of every
sign-out, and no evidence here proves that cookie expiry or device-bound-session
controls caused the recent incident. Human login restored actual project access.

The service already reuses a persistent hosted profile. Login and generation use
the same profile directory and `--password-store=basic`; the generation browser
uses that profile's recorded browser channel. The deployed runtime is headed.
Normal operations do not clear cookies or recreate the profile, and the client
closes its context/driver before releasing the profile lease. These measures
reduce local state loss and concurrent-browser corruption; they cannot prevent
Google from revoking a session or asking for another identity check. Keep the
original hosted profile and complete any challenge there. Workstation login
instructions should use Vivaldi; the dedicated hosted runtime remains distinct.

## Login persistence priority — 4 October 2026

Session retention and automatic renewal are separate requirements. Persistent
browser storage alone is not unattended authentication management.

A read-only operator comparison found all three matching Google accounts still
registered on UseAPI's current Flow backend with health OK, credit/model fields,
session-expiry timestamps and refreshes scheduled one hour before those timestamps.
The latest returned CAPTCHA activity was 3 October at00:39UTC; the jobs read listed
no active jobs. Those are provider observations, not proof that simultaneous use
caused gflow's failures. UseAPI describes exclusive management of the API session
and warns about direct Flow access in its
[setup guide](https://useapi.net/docs/start-here/setup-google-flow).

The local cookie-reader fallback had a reproducible persistence bug: its cold
Chrome launch lacked the restoration argument already used by the shared
generation client. A network-isolated real Chrome regression seeded synthetic
Session SSO/app cookies, closed Chrome, and called the actual reader. Before the
correction, the reader returned zero cookies and lost the SSO signal. The corrected
reader retains both cookies, still with Session expiry, through three cold reads.
The headless verifier, shared login-launch helper, bare Chrome fallback and
standalone UI transport now use the same guarded retention rule. The already
guarded migrated verifier inherits the helper without duplicating the argument.

Retention applies only to an owned private Chrome-marked profile with the existing
private account marker. It does not authenticate the marker, extend cookie expiry,
change engines, replay a job, or prove current identity. First-login verification
before an account marker is written remains a separate acceptance case. Restoring
a browser session can reopen old tabs and start background traffic.

This bug is not established as the cause of the current three-account failure.
The original hosted profiles still contained unexpired persistent Google/Flow
cookies. A bounded pro3 browser trace retained those cookies but landed at Flow's
public /about page, got401 on the fresh People read, and landed at Google's public
account page on the independent MyAccount read. No generation or solver call was
made. Retaining a stored cookie does not make a refused session valid.

Automatic renewal remains missing. Do not mark R10 or unattended operation complete
until an authenticated hosted session survives cold reopen, service restart, idle
time and an observed renewal boundary without another human login. Capture the
actual supported renewal behavior and keep a single serialized owner before
implementing a timer; repeatedly launching health checks is not renewal.


The operator subsequently reserved one account for UseAPI and disconnected the
other two for gflow-only testing. Both UseAPI account removals returned200 and a
fresh list verified the single retained healthy registration. gflow REST selection
excludes the retained profile, and hosted CLI/MCP defaults use a test profile.
This removes overlapping managed use during subsequent testing without establishing
that it caused the original failure. See [verification](VERIFICATION.md#4-october-session-persistence-correction-and-isolated-test-accounts).

## On-demand actual access check

`POST /v1/google-flow/accounts/{handle}/health` is a self-hosted extension. It
accepts a JSON object with optional `async`, `replyRef` and allowlisted `replyUrl`.
It uses the selected registered profile and its configured project. It does not
accept a replacement project, profile path, cookies, or credentials.

```http
POST /v1/google-flow/accounts/my-account/health
Authorization: Bearer YOUR_SERVICE_TOKEN
Content-Type: application/json

{"async": true}
```

An asynchronous check returns 201 with the existing job polling identity and
Location. The check waits behind accepted jobs in the same durable per-profile
queue; it never opens a competing browser from the HTTP handler. Synchronous
requests use the [normal bounded wait](HTTP_JOB_SEMANTICS.md). Poll the same job
when the HTTP wait expires; do not treat a timeout as a login diagnosis.

The terminal job contains `response.sessionHealth` and its tested `projectId`:

```json
{
  "health": "OK",
  "reason": "project_access_verified",
  "source": "native-project-access",
  "checkedAt": "2026-10-03T12:00:00.000Z",
  "profilePreserved": true,
  "refreshAttempted": false
}
```

| Observation | Meaning |
|---|---|
| `OK` / `project_access_verified` | A native project read succeeded at `checkedAt`; this is not a future-login guarantee or a fresh Google-principal proof. |
| `LOGIN_REQUIRED` / `login_required` | The existing client raised an explicit authentication-missing or expired error; complete human login in the original hosted profile. |
| `UNKNOWN` / `identity_unavailable` or `identity_changed` | The private marker was absent or inconsistent; this alone does not prove that the Google session expired. |
| `UNKNOWN` / `profile_busy` | Another owner holds the browser profile; no process is interrupted or killed by the health probe. |
| `UNKNOWN` / `probe_timeout`, `probe_error` or `interrupted` | The read could not establish access, or the daemon stopped; no auth refresh or billable operation is replayed. |

The native read has a 90-second probe deadline with the client's existing bounded
cleanup allowance. The daemon also applies its configured subprocess timeout.
The result is a timestamped observation; historical successful jobs can be
inspected separately. It does not overwrite enabled/verified registration flags,
which remain operator or prior-import attestations. A network or selector failure
therefore cannot silently disable an account.

The on-demand check performs no cookie copying, automatic reauthentication,
challenge bypass, generation, CAPTCHA solve, or paid operation. Optional periodic
project-access scheduling is described below; it is separate from renewal.
Public output contains fixed statuses and metadata rather than timeline data,
cookie values, raw exception messages, or signed URLs.

## Optional idle project-access maintenance

Set `GFLOW_SELFHOST_IDLE_SESSION_INTERVAL_SECONDS=1800` or a longer finite interval
in the daemon environment and restart the service to enable periodic ordinary
project access. The default is `0`, which performs no scheduled reads. This can
exercise a saved session during idle time; whether Google naturally maintains
that session is unverified. It does not extend a cookie, authenticate a private
marker, refresh login, prevent a human identity challenge, or complete R10's
unattended-renewal acceptance.

The scheduler admits the existing `accounts/health` job only when its currently
enabled, verified profile is due and has no created/running queue work. Disabled,
unverified and removed registrations are skipped, including the reserved disabled
account. There is at most one outstanding maintenance job across the daemon.
The first due time is registration time plus the configured interval; an older
idle registration can be due immediately when scheduling is first enabled.
SQLite admission and a small registration-scoped scheduler record survive
restart. A profile/email/project mapping change resets the scheduler record,
including a change followed by a reversion; stale queued reads cannot regain
permission from matching old field values.

The existing serial worker owns the bounded native read and browser teardown.
There is no resident browser or generation/solver/login/cookie-transfer operation.
A CLI or MCP operation holding the profile lease remains authoritative: the health
probe reports UNKNOWN/profile_busy and backs off rather than opening a competing
browser or killing its owner. A generation accepted after maintenance admission
can wait behind that bounded health read.

Successful maintenance schedules the next check one interval after completion.
UNKNOWN observations wait twice the interval, and LOGIN_REQUIRED observations
wait four times the interval. Backoff is capped at 24 hours without shortening
an operator interval already longer than 24 hours. Complete any human verification
in the original hosted profile before using the on-demand health route to confirm
access. Failure never changes account enabled/verified attestation.

`GET /accounts` and `GET /accounts/{handle}` expose a separate
`idleSessionMaintenance` object: `enabled`, `intervalSeconds`,
`mode: "periodic-project-access"`, `refreshAttempted: false`, `state`,
`nextDueAt`, `lastJobId` and `lastObservation`. `nextDueAt` is a Unix timestamp
in seconds, or null while disabled/pending. State is disabled, due, waiting,
queue_busy or pending. A global outstanding read can defer a due idle profile;
that profile remains due until admitted. `lastObservation` is the existing fixed
public health projection, or null before a completed check; raw principal,
cookies, URLs and errors are omitted. Registration `health` keeps its existing
attestation meaning. Poll `lastJobId` through the normal job route for its result.

The queue now uses schema5. An older schema4 binary rejects this database; the
immediate rollback is interval `0` on the current binary, preserving the queue.

To stop scheduling, set the interval to `0` and restart. Before workers start,
only scheduler-origin checks still in the created state are canceled. Manual
health requests, active reads and generation jobs are preserved; a canceled
maintenance job reports no new health observation. Restart recovery keeps the
existing interrupted-health UNKNOWN behavior and never replays that read.
Disabling a registration through the existing account route also cancels its
queued maintenance. If an active/manual/generation job still occupies the
profile, the existing busy refusal remains; wait for it to finish before disabling.
No browser profile is deleted or signed out.

Offline tests cover admission races, one global outstanding job, restart,
configuration/account disable, manual-work preservation, registration reversion,
backoff, pre-subprocess guards, private status projection and daemon cancellation.
An actual scheduled native read is pending parent-coordinated testing; these
checks do not establish idle-time or renewal-boundary survival.

## Verification

Offline tests cover queue serialization, account/project binding, bearer access,
idempotency, actual-read success, typed auth failure, contention, identity changes,
network/timeout/close errors, cancellation, and interrupted read-only recovery.
Fake browser-context tests also exercise importer close/cancellation and fallback.
An isolated real HTTP service on CC LXC subsequently passed the native queue
check: HTTP401 without authentication, HTTP201 for asynchronous acceptance,
then completed with OK actual project access. The published checkpoint was then deployed on CC LXC and the production
HTTP queue passed the same check after reopening the persistent profile.

The shared health helper was subsequently exercised against the original hosted
account after manual identity verification: OK/project_access_verified,
profilePreserved true, refreshAttempted false. That is real native project-access
evidence. The isolated real HTTP queue proof confirmed those same flags without
generation. The production-service smoke subsequently passed as well.

Production proof: authenticated capability discovery advertises the new routes;
HTTP401 without bearer, async HTTP201, completed OK/project_access_verified,
profilePreserved true and refreshAttempted false. At that earlier checkpoint the registered MCP service
exposed 22 tools, including the updated image reference and native voice schema.
No generation or CAPTCHA task was performed by the health/protocol checks.

Four subsequent SDK, CLI, registered-MCP and HTTP synthetic upload/archive BDD
runs reused the original saved login, with fresh native project reads confirming
access after each lifecycle. No further manual identity challenge was required
during those tests. This is observed session reuse, not a guarantee that Google
will never ask for verification again.

The later portable-media deployment exposed 24 registered MCP tools. Its fresh production health job again verified native project access with the original profile preserved and no refresh. See the [current verification ledger](VERIFICATION.md) for the dated checkpoints.

## Browser lifecycle and measured memory

The request lifecycle opens a headed browser against the selected persistent
account profile and closes it after the operation. An idle account keeps its
profile on disk and has no dedicated Chrome processes. REST, MCP and the settings
GUI remain running; this is not a per-account browser keepalive.

After isolating accounts from UseAPI, a human login on the second test profile
passed two cold opens with fresh native current-account and project-access reads.
The same proof passed after restarting the idle REST/MCP services, then after a
real single-image API job and its native2K upscale. Outputs decoded to1024x1024
and2048x2048 respectively; no external CAPTCHA solver was used. This proves
reuse through those operations, not long-idle or automatic-renewal acceptance.

Memory checks exposed restored-tab accumulation: the old client reused only one
restored tab and opened new pool pages while keeping the other restored tabs.
A real-browser regression observed11 then13 context pages at concurrency2,
while fresh identity still matched. The client now reuses restored tabs up to
the pool size and closes the surplus. Its real-browser regression passed with
exactly2 tabs on both cold opens and the same freshly read principal. Login
restoration and the profile lease remain in place.

With the default one-page pool on CC LXC, two subsequent actual account/project
reads measured541 and607MiB of aggregate proportional set size (PSS) for that
profile's browser process tree. Both closes left zero browser processes and
zero browser RAM attributable to the profile. The earlier growing-tab case
reached1534MiB. These are read-workload observations, not generation peaks:
budget roughly0.6–1GiB per simultaneously active account with extra headroom for
generation. REST, MCP and GUI main processes together measured179MiB PSS,
excluding workers, Xvfb/noVNC and OS overhead.

Run the read-only regression explicitly with a logged-in testing profile:

    export GFLOW_CLI_E2E_HOME="$GFLOW_CLI_HOME"
    export GFLOW_CLI_E2E_PROFILE=YOUR_TEST_PROFILE
    export GFLOW_CLI_E2E_PAGE_POOL_REUSE=1
    .venv/bin/python -m pytest -q -m e2e_auth tests/e2e/test_restored_page_pool_bdd.py

It opens the selected profile twice and performs fresh identity reads without
generation. Automatic renewal is still missing. Keeping Chrome open has not
been established as necessary or sufficient for long-term renewal.

## Login completion correction and unresolved renewal

A later second-account check returned native HTTP401 and Flow/MyAccount public
landings despite retained, unexpired cookies. This followed a staged cookie-import
attempt; the timing does not establish its cause. Further live cookie-copy/import
experiments are suspended. That account was temporarily disabled for automatic gflow selection during
recovery. After the corrected human login it passed two fresh current-principal
and project-access cold opens and was re-enabled. The third test account remains
the hosted CLI/MCP default; both testing accounts are enabled. The retained UseAPI account remains disabled in gflow.

The second-account recovery exposed a separate gflow defect: its login detector
closed Chrome on the migrated cookie pair, then the independent saved-profile
verifier rejected the session. Thus a black viewer and a successful service exit
alone do not establish successful authentication.

The detector now requires a fresh native current-principal read before migrated
auto-close, handles refusal inside the wait loop, bounds that read by the remaining
login deadline and checks the page again afterwards. Labs verification, profile
leases, disk verification and expected-account matching remain in place. The login
browser also uses the configured engine. No keepalive or renewal timer was added.

Three unit regressions reproduced the early stop before the fix. The real-browser,
intercepted native401 scenario also failed before it and passed afterwards.
A separate real Google check on the third account passed live identity detection,
normal auto-close and independent saved-profile verification, without generation
or solver requests. The second account's corrected human recovery succeeded, including independent
saved-profile verification and two fresh project-access cold opens.
Automatic renewal and long-idle survival remain open acceptance requirements.
