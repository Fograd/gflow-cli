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

There is no periodic browser keepalive, cookie copying, automatic reauthentication,
challenge bypass, generation, CAPTCHA solve, or paid operation in this check.
Public output contains fixed statuses and metadata rather than timeline data,
cookie values, raw exception messages, or signed URLs.

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
