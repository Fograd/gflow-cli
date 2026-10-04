"""Private source-backed image upscale token/provider bridge, with no credential argv."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image_upscale import TargetResolution, UpsampleImageRequest
from gflow_cli.config import get_settings
from gflow_cli.selfhost.native_captcha_policy import run_with_native_captcha_policy


async def upscale(profile: str, project: str, request_path: Path) -> None:
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    resolution = TargetResolution.from_cli(payload["resolution"])
    UpsampleImageRequest(
        media_id=payload["mediaGenerationId"], project_id=project, target_resolution=resolution
    )
    settings = get_settings()
    out = request_path.parent

    async def attempt() -> None:
        async with FlowApiClient(
            profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
        ) as client:
            await client.upsample_image(
                media_id=payload["mediaGenerationId"],
                project_id=project,
                target_resolution=resolution,
                out_path=out / "upscaled.png",
            )

    await run_with_native_captcha_policy(payload, project, "IMAGE_GENERATION", attempt)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(2)
    profile, project, request_path = sys.argv[1:]
    run_with_handlers(
        lambda: upscale(profile, project, Path(request_path)), cli_command="image upscale"
    )


if __name__ == "__main__":
    main()
