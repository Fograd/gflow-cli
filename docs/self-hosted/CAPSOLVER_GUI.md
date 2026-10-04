# Private CapSolver key editor

This small local page saves/removes a CapSolver key and checks its balance through the fixed CapSolver endpoint. It never creates a paid solving task. Storage and a successful balance check do not prove Google Flow accepts a solver token: fresh native metadata is measured and explicit image/native provider controls are implemented. Saving a key never silently selects paid solves. The generationEnabled status means configured capability, not accepted Google output. See [CAPTCHA controls and limits](CAPTCHA.md).

## Start and open

Run as the same service user as the Flow API so both use the private `~/.config/homelab/secrets.env` file:

```bash
cd ~/workspace/gflow-host/source
.venv/bin/python -m gflow_cli.selfhost.admin
```

The page binds only to `127.0.0.1:8845`. It does not require or expose the Flow REST bearer. Forward the port from your workstation:

```bash
ssh -N -L 127.0.0.1:8845:127.0.0.1:8845 USER@HOST
```

Open `http://127.0.0.1:8845/` in Vivaldi. Enter the key, select Save, then Check connection to read balance using the saved key. Remove clears only the CapSolver key. Status is masked; the page never reads a stored key back into the form. Do not share a screenshot containing a key you have entered. Close the browser tab and tunnel when finished.

An optional `GFLOW_CAPSOLVER_GUI_PORT` changes the listening port; update both SSH forwarding and URL to match. The host remains loopback. Do not expose this editor through a reverse proxy or bind it to a LAN interface: it is intended for one trusted service user with SSH access.

## Run as a service

Copy [gflow-capsolver-gui.service](../../deploy/selfhost/gflow-capsolver-gui.service) into `~/.config/systemd/user/`, adjusting checkout paths when needed:

```bash
systemctl --user daemon-reload
systemctl --user enable --now gflow-capsolver-gui
systemctl --user status gflow-capsolver-gui
```

This editor does not need the headed display, Chrome profiles or REST bearer environment. ProviderKeys atomically preserves unrelated secrets-file lines and keeps the file private. Back it up under the same protections as other credentials.

## Connection failures and boundaries

A rejected or expired key must be corrected with your CapSolver account. A timeout or provider failure does not remove the saved key. Balance requests have a deadline of 15 seconds and streamed 64KiB response limit, and only one check runs at a time. These checks cannot incur task fees.

Exact loopback Host/Origin checks, a process-scoped CSRF header, nonce CSP, no-store and frame-denial headers protect the local page. They do not provide multi-user authentication: keep the host and SSH credentials private. Provider bodies, API keys and raw exception details are never displayed in error responses.

A configured key was independently exercised once: CapSolver returned a solution, but Google rejected the replaced image request for unusual activity. No accepted image or automatic retry resulted. The page continues to report generation disabled; its balance check itself never creates a task.
