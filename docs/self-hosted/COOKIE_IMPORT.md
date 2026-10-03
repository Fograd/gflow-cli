# Cookie import and refresh

POST `/v1/google-flow/accounts` accepts a `cookies` string copied as a Chromium
DevTools cookie table. The CLI accepts the same table through a private file:

```sh
gflow auth import-cookies --cookies-file /private/cookies.tsv \
  --profile imported-account --expected-email operator@example.com \
  --project 11111111-1111-4111-8111-111111111111 --json
```

A new profile name is required. The command does not select it as the CLI default
or register it with the self-hosted API. Use `gflow auth use imported-account`
to select it, or the account registration API to make it available to workers.
`--expected-email` is the actual Google principal, rather than a local account
alias. `--project` checks access to a specific existing project; without it the
importer discovers an existing native project and verifies access.

This operator credential operation is CLI-only. MCP does not accept cookie
values, credential files, or enqueue profile imports. Its existing read-only auth
status remains available. HTTP import is protected by the service bearer token.

## Accepted table format

The table must be UTF-8, at most 1 MiB, with one to 256 cookie rows. Values are
limited to 16 KiB each. The CLI refuses symlink inputs, nonregular files and files
that change during reading. No argument, success response or parser error
contains cookie values.

Headerless tables have five to eleven tab-separated columns, in this order:

```text
Name  Value  Domain  Path  Expires  Size  HttpOnly  Secure  SameSite  Partition Key  Priority
```

Tabs, including empty fields, must be preserved. A named header may reorder
these supported columns, but must contain the first five, have unique known
column names and match every row's column count. `Expires / Max-Age` is an alias
for the absolute expiry column; relative max-age numbers are not supported.

Expiry is `Session`, an ISO date with an explicit timezone, or absolute Unix
seconds. Session cookies omit the Playwright expiry field. Expired dates,
nonfinite values and timezone-free dates are refused. Boolean columns accept
empty/false or true/checkmark. SameSite accepts empty, Strict, Lax or None;
empty remains unspecified. None requires Secure. Cookie prefixes retain their
host/path/secure constraints. Priority accepts empty, Low, Medium or High.

The exact domain allowlist is google.com, accounts.google.com, labs.google and
flow.google.com, with or without their leading dot. Host-only and domain cookies
retain that distinction. Other domains, duplicate name/domain/path identities,
nonempty partition keys, unknown columns and ambiguous rows are refused.

The parser refuses `__Secure-1PSIDRTS`, following the device-bound-session check
in the [useapi setup guide](https://useapi.net/docs/start-here/setup-google-flow).
A syntactically valid table does not prove that another device can use its
session. Prefer the hosted browser login when transfer is rejected. Use Vivaldi
for workstation instructions; the hosted gflow runtime currently requires its
own system Chrome profile.

## Activation and failures

Cookies are installed into a private staged profile, with the normal profile
lease and headed Chrome launch. A bounded live Google identity check must match
the expected principal, and a native project read must establish actual Flow
access before the candidate is activated. A cookies file, a chooser row, or a
successful parse never marks the profile authenticated.

The original profile is preserved. Refresh uses a new version profile and an
atomic account-mapping switch after both profiles are idle; historical jobs keep
their original profile identity. Failed or cancelled candidates are normally removed; OS-denied cleanup retains a private unactivated quarantine as described below.
Rollback cleanup refuses busy, replaced or subsequently changed imports rather
than deleting a profile it can no longer prove it owns.

Responses contain safe account/project/profile metadata. Unlike useapi, this
service does not echo accountCookies, sessionCookies, access_token or sessionData.
Automatic scheduled refresh before expiry is not established by cookie import.

## Verification status

Parser, staging/rollback and CLI adapter invariants have offline tests. On
2026-10-03 a private isolated copy of the logged-in session contained 27 allowed
cookies and no device-bound marker. The candidate failed live authentication
verification and was removed; no account mapping or original profile was changed.
Cookie import is therefore implemented with safe rejection, while successful
live acceptance remains pending. At that earlier diagnostic point, the original profile also landed on
Flow's public about page during a later separate native read; that observation
does not establish whether cookie copying caused the state.

See [API reference](API.md), [parity matrix](PARITY.md), and
[verification ledger](VERIFICATION.md) for the remaining account/session gaps.

## Registration, refresh and browser-column limits

POSTaccounts accepts cookies alone and creates a new versioned private profile;
new registrations return201 and verified refreshes return200. Account handles
remain stable. Refresh preserves the previous creation time, project and original
browser profile, while atomically selecting the newly verified profile. An
existing account's bounded saved identity marker is required to prove that a
refresh belongs to the same Google principal. Active jobs prevent refresh.

The JSON account-request ceiling is2MiB; the cookie table itself is bounded
to1MiB. Registration verification records what succeeded at that time; it is not
a promise that Google will never request another identity check. Browser Priority
cells are validated as empty/Low/Medium/High but are not applied through
Playwright's cookie API. Partitioned cookies and unsupported device-bound
cookie markers are refused before launch.

The original browser session is retained after a failed clone. Do not repeatedly
copy or replace the active profile to address a verification prompt. Complete
Google's challenge using the same hosted profile; subsequent actual project
access is checked separately from cookie presence.

If the operating system denies candidate cleanup, the original error or
cancellation is preserved with a safe cleanup-pending note. The unactivated
candidate may remain in the private700 staging directory for operator removal;
it is not registered or silently treated as deleted. Structured logs record
cleanup-pending flags, without raw exceptions, cookie values or candidate paths.

After the user completed Google's identity challenge in the original hosted
profile, actual project access and a single canonical reference/character image
generation succeeded. Repeated normal context closures/reopenings retained
session access. This verifies restored original-profile operation, not cookie
transfer acceptance, and does not establish the cause of the earlier challenge.
