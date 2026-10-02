"""Run the REST adapter with ``python -m gflow_cli.selfhost``."""

import os

import uvicorn

from gflow_cli.selfhost.server import Settings, create_app


def main() -> None:
    uvicorn.run(
        create_app(Settings.environment()),
        host=os.environ.get("GFLOW_SELFHOST_HOST", "127.0.0.1"),
        port=int(os.environ.get("GFLOW_SELFHOST_PORT", "8844")),
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
