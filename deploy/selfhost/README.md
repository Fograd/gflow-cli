# Single-user Flow API service

The service uses the existing headed Chrome display and saved profile directories.
Create the environment file documented in [the API guide](../../docs/self-hosted/API.md).
Keep the bearer token in a protected environment file outside this checkout.
Copy `gflow-api.service` into the user's systemd unit directory, adjust paths to your checkout,
and use `systemctl --user daemon-reload` followed by `systemctl --user enable --now gflow-api`.

The sample uses a separate REST port from the existing MCP daemon.
Select a private bind address reachable from your tool container, or use loopback with SSH forwarding.
Authenticate all API requests with `Authorization: Bearer <token>`.

Do not run two processes against the same Chrome profile outside the profile lease.
Stopping a worker during a generation leaves the job interrupted; inspect it before submitting another.
