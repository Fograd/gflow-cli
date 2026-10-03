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
then completed with OK actual project access. Production-service smoke
verification remains a separate deployment step.

The shared health helper was subsequently exercised against the original hosted
account after manual identity verification: OK/project_access_verified,
profilePreserved true, refreshAttempted false. That is real native project-access
evidence. The isolated real HTTP queue proof confirmed those same flags without
generation; production-service smoke verification is separate.
