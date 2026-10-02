"""Internal upload subprocess: inherit the existing SDK's Chrome profile lease."""

import sys
from pathlib import Path

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings


async def upload(profile: str, project: str, path: Path) -> None:
    settings = get_settings()
    async with FlowApiClient(
        profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=path.parent
    ) as client:
        asset = await client.upload_reference(project, path)
        json_output.emit({"status": "ok", "media_id": asset.name, "project_id": project})


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(2)
    profile, project, path = sys.argv[1:]
    run_with_handlers(
        lambda: upload(profile, project, Path(path)), cli_command="selfhost upload", as_json=True
    )


if __name__ == "__main__":
    main()
