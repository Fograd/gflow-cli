# Single-user Flow API deployment

Use [the complete setup guide](../../docs/self-hosted/OPERATIONS.md) for installation, display/login, three independent profiles, environment files and backups. [The API guide](../../docs/self-hosted/API.md) describes requests; [the migration guide](../../docs/self-hosted/MIGRATION.md) describes tee integration. Current native/local coverage and gaps are explicit in [the compatibility inventory](../../docs/self-hosted/PARITY.md).

Use Vivaldi on your workstation for the forwarded noVNC login viewer. The current remote automation engine requires an existing headed Chrome display and saved profiles on the LXC; workstation Chrome is unnecessary. [gflow-api.service](gflow-api.service) is a user systemd unit. It loads common gflow configuration, separate self-hosted configuration and a protected secrets file outside the checkout. Adjust its paths to your service user's checkout before installation.

```bash
mkdir -p "$HOME/.config/systemd/user"
cp deploy/selfhost/gflow-api.service "$HOME/.config/systemd/user/gflow-api.service"
systemctl --user daemon-reload
systemctl --user enable --now gflow-api
systemctl --user status gflow-api
```

The sample depends on `gflow-display.service`; create and start that unit as described in the setup guide. Configure `GFLOW_DAEMON_TOKEN`, `GFLOW_SELFHOST_ROOT` and `GFLOW_SELFHOST_ACCOUNTS` before starting. Keep every environment file private. Enable only profiles whose login and generation were checked. The three accounts have separate limits and project UUIDs.

REST defaults to loopback port8844, independent of the existing MCP daemon. Set `GFLOW_SELFHOST_HOST` explicitly for a private LAN or use SSH forwarding. Authenticate every request with a bearer header. The schema at `/openapi.json` is authenticated. No password or Google cookies are returned by the service.

A serial worker owns each profile; the SDK's profile lease also coordinates REST/MCP/CLI browser access. Drain work before restarts where possible. A generation stopped midway becomes `interrupted` on restart and is never automatically billed again. Inspect Google and local outputs before explicit retry. Back up queue, saved profiles and outputs together; see the setup guide's consistent-backup procedure.

Successful native2K is recorded in [the deployment verification ledger](../../docs/self-hosted/VERIFICATION.md). Paid video generation, other profiles and Ultra4K must not be described as verified unless that ledger records the evidence.
