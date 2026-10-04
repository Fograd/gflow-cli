# Setup and operation

Use Vivaldi on your workstation to open the login viewer and API documentation. The current remote automation runs as one trusted user's process, using real headed Chrome under a display server; that engine choice is separate from your personal browser preference. A private LXC with Python3.11+, Google Chrome, `uv`, Xvfb and sufficient persistent disk is appropriate. FFmpeg/ffprobe are needed for local video concatenation. The standard upstream health-check container image does not include this browser deployment; see [container limitations](../CONTAINER.md).

## Install the fork

```bash
mkdir -p "$HOME/workspace/gflow-host"
cd "$HOME/workspace/gflow-host"
git clone --branch feature/self-hosted-flow-api https://github.com/Fograd/gflow-cli.git source
cd source
uv sync --frozen --extra patchright
```

Use the checkout's `.venv/bin/gflow`, not a separately installed upstream `gflow` command. `uv sync --frozen --extra patchright` installs the project's Python dependencies. The current configured remote engine requires real Google Chrome on the LXC through its official Linux package; it does not require Chrome on your workstation. On Debian/Ubuntu, install `xvfb`, `x11vnc`, `novnc`, `websockify` and `ffmpeg` through your normal package manager. Upstream's [authentication guide](../AUTHENTICATION.md) explains Chrome profile creation and Google identity rechecks.

Keep the installation extra and service environment consistent: this deployment
uses `GFLOW_CLI_BROWSER_ENGINE=patchright` and the locked `patchright` extra.
The service still launches the saved profile through real system Chrome.
Use `.venv/bin/gflow` or `.venv/bin/python` for operator commands. If using `uv run`,
include `--extra patchright`; a default sync/run can remove the optional dependency.
This is an explicit deployment choice; the upstream default engine is unchanged.
Before switching engines, drain both REST and MCP queues and preserve the profiles.
The 4 October production read proof is recorded in [verification](VERIFICATION.md).

## Persistent headed display

Create a user systemd unit at `~/.config/systemd/user/gflow-display.service`:

```ini
[Unit]
Description=Headed display for Google Flow

[Service]
ExecStart=/usr/bin/Xvfb :93 -screen 0 1440x1000x24 -nolisten tcp
Restart=on-failure
UMask=0077

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gflow-display
```

If the user service must start before an interactive login, enable systemd user lingering through the host's normal administrator workflow. Keep display number, `DISPLAY` and VNC settings consistent.

## Environment and credentials

Create separate protected environment files outside the checkout. The sample unit loads these paths:

- `~/workspace/gflow-host/environment`: headed display and gflow paths.
- `~/workspace/gflow-host/selfhost/environment`: REST configuration and enabled accounts.
- `~/.config/homelab/secrets.env`: bearer token and any solver credentials supported by the deployed build.

Example common environment:

```dotenv
DISPLAY=:93
GFLOW_CLI_HOME=/home/USER/.local/share/gflow-host/profiles
GFLOW_CLI_OUTPUT_DIR=/home/USER/.local/share/gflow-host/output
GFLOW_CLI_HEADLESS=false
GFLOW_CLI_BROWSER_ENGINE=patchright
GFLOW_CLI_AUTH_LOGIN_TIMEOUT=7200
```

Replace `/home/USER` with the service user's actual home. Example REST environment, initially with no enabled accounts:

```dotenv
GFLOW_SELFHOST_HOST=127.0.0.1
GFLOW_SELFHOST_PORT=8844
GFLOW_SELFHOST_ROOT=/home/USER/.local/share/gflow-host/selfhost
GFLOW_SELFHOST_ACCOUNTS='{}'
GFLOW_SELFHOST_ALLOW_VIDEO=0
GFLOW_SELFHOST_CALLBACK_HOSTS=
```

Generate a long random bearer token and save it as `GFLOW_DAEMON_TOKEN` in the secrets file. Do not paste it into a URL or commit it. Set environment files to mode600 and their directories to700. Keep profiles, uploads, queue and backups private.

Shell commands in this guide require the common environment to be loaded. For a file containing the example shell-compatible entries:

```bash
set -a
. "$HOME/workspace/gflow-host/environment"
set +a
```

The service reads its own environment files through systemd; an unrelated shell's variables do not configure that running service.

## Log in each Google account

Expose the display temporarily through loopback VNC. Run the VNC and web proxy in separate terminals while logging in:

```bash
x11vnc -display :93 -localhost -rfbport 5993 -nopw -forever -shared
```

```bash
websockify --web /usr/share/novnc 127.0.0.1:6093 127.0.0.1:5993
```

Forward loopback ports from your workstation; replace USER/HOST with the SSH destination:

```bash
ssh -N -L 127.0.0.1:6093:127.0.0.1:6093 \
       -L 127.0.0.1:8844:127.0.0.1:8844 USER@HOST
```

Open `http://127.0.0.1:6093/vnc.html?autoconnect=true&resize=scale` in Vivaldi on your workstation, then run one login at a time on the LXC:

```bash
.venv/bin/gflow auth login --browser chrome --profile pro1
.venv/bin/gflow auth status --profile pro1
```

Complete Google login yourself, including any identity recheck. The API never needs your password. Repeat with `pro2` and `pro3` after each previous browser has closed. Stop the temporary VNC/web proxy when login work is finished; the Xvfb display stays running for generation.

Create or select one Flow project per profile through the CLI and record its UUID privately. Generate a test image through that profile, then verify native2K dimensions. Only after success add that profile to `GFLOW_SELFHOST_ACCOUNTS`. Example structure with placeholder UUIDs:

```dotenv
GFLOW_SELFHOST_ACCOUNTS='{"pro1":{"email":"account-one","project":"11111111-1111-4111-8111-111111111111"},"pro2":{"email":"account-two","project":"22222222-2222-4222-8222-222222222222"},"pro3":{"email":"account-three","project":"33333333-3333-4333-8333-333333333333"}}'
```

Replace every placeholder with its own real project UUID. The aliases are public API handles; the browser profiles determine the Google identities. Three Pro plans give three independent allowances. They do not combine into an Ultra account, and successful4K is not enabled by owning three Pro plans. All three profiles have historical read-only proofs; latest access and expiry observations are in the deployment [ledger](VERIFICATION.md). Recheck the selected profile before a new campaign.

## Start and inspect the REST service

Copy [the sample unit](../../deploy/selfhost/gflow-api.service) into `~/.config/systemd/user/`, adjusting checkout and environment paths if needed:

```bash
systemctl --user daemon-reload
systemctl --user enable --now gflow-api
systemctl --user status gflow-api
journalctl --user -u gflow-api -n 50 --no-pager
```

Use [the API example](API.md#requests) to submit and poll a job. `/capabilities` and `/openapi.json` require the bearer token. An unauthenticated401 is expected. Set `GFLOW_SELFHOST_HOST` explicitly for private LAN access; keep loopback plus SSH forwarding across untrusted networks. The REST service uses port8844 independently of the upstream MCP daemon.

A serial worker runs for each enabled profile, and profile leases coordinate Chrome access across CLI, MCP and REST. An operation already using a profile may delay or reject a second caller. Do not kill Chrome to defeat the lease. `health: "OK"` means operator-enabled configuration, not a fresh quota/entitlement query.

After changing an environment file, restart the service so it loads the new configuration. Drain running jobs first where practical. Accepted jobs survive an HTTP client disconnect. A running job interrupted by daemon shutdown is never automatically resubmitted.

## Failures and recovery

| Symptom | Action |
|---|---|
|401 | Check bearer header and that client/service use the same protected token. |
| `upload_rights_required` | Confirm rights interactively, or make a new MP4 request with exact `X-Flow-Rights-Confirmed: true` and a new idempotency key only when you have those rights. |
|422 | Correct input types, ownership or model/mode restrictions before resubmitting. |
|501 | Consult the inventory; the requested endpoint/control is not implemented in this build. |
|429 | Respect Retry-After. Poll an accepted job instead of creating a replacement. |
|`interrupted` / `submission_outcome_unknown` | Inspect the Flow project and local outputs before explicitly retrying; Google may have accepted the operation. |
|Google identity recheck or/about landing page | Stop new work for that profile and finish interactive login using its saved Chrome profile. |
|Selector drift / unavailable2K menu | Record host, operation and sanitized error. Reproduce on the current UI; do not infer plan limits from a missing selector. |
|Pro4K refusal | Expected entitlement restriction. Use2K or an authenticated Ultra profile. |

Callbacks use an exact public HTTPS hostname allowlist, pinned DNS, no redirects and a durable outbox. Private LAN callbacks are currently unsupported. The outbox attempts delivery up to five times; receivers deduplicate by job ID and status. Use polling when no callback destination is available. A callback delivery failure does not repeat generation.

## Preserving the saved login

Keep the full original browser profile on persistent LXC storage, under the same service user and configured profile path. Normal code updates preserve it. All CLI, MCP and REST access must use the profile lease; never open a second Chrome process against that directory or kill a browser to bypass contention. Do not clear the profile, replace it with a cookie-only export, or switch its browser engine as a routine response to an access failure.

The on-demand account health action verifies native project access through the serialized worker. An OK result proves access at its recorded time; it does not renew login or promise future access. A profile-busy, timeout or unknown result is not evidence of logout. See [the session health contract](SESSION_HEALTH.md) and [the measured restoration ledger](VERIFICATION.md).

In the recorded incident Google requested human identity verification while the original saved account remained available. The cause was not established. Completing that challenge restored access, and repeated browser closures and reopenings reused the same login. No permanent prevention of Google identity checks has been demonstrated. If verification is requested again, complete it in the existing hosted profile, then recheck project access before resuming work. Repeated automated login attempts or periodic health reads are not a verified remedy.

## Backup and restore

For a consistent backup, stop accepting new requests, wait for running jobs to finish, then stop REST/MCP and any process using the saved profiles. Back up the complete persistent gflow home, self-host queue directory and all SQLite companion WAL/SHM files if present, uploads, outputs, enabled-account environment and saved browser profiles. Back up secrets separately under equivalent access controls. Copying only `jobs.sqlite3` while it is live can miss WAL transactions.

Protect backups like logged-in accounts: Chrome profiles contain session credentials. Keep them out of GitHub and shared documentation. During restore, use the same service user and configured paths/permissions, restore profiles and queue together, then start Xvfb and the service. Test read-only auth and a known completed job before accepting new generations. Restored Google sessions can require an interactive identity recheck.

## Updates and rollback

Record the current checkout commit and back up persistent state before updating. Stop services after jobs drain, fetch and check out the intended fork revision, run `uv sync --frozen --extra patchright`, run the applicable offline checks, then restart. Verify one known image/upscale operation before widening traffic. See [the verification ledger](VERIFICATION.md) for checks actually performed.

Rollback to the recorded code revision and its compatible environment; do not erase persistent jobs. Queue schema incompatibility is an explicit startup error rather than silent migration. A new operation must use a fresh idempotency key; a network retry must keep its original key/body. Never replay interrupted billed work solely because code was rolled back.

## Character metadata operations

The verified native character flow copies one or two existing images from its owning project, applies initial notes and supports later name/notes/system preset updates, detail reads and removal. Use explicit account/project controls from [the API example](API.md); retain returned references. It copies existing images and assigns system presets as metadata; generation binding and rendered speech remain separate work. A partial HTTP 502 may include a created character reference: inspect it before retrying instead of creating another draft. Source images remain separate from copied character workflows. Remove test characters after verification through their exact owned references.
