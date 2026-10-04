"""Private measured 2K upscale token/provider bridge, with no credential argv."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.config import get_settings
from gflow_cli.selfhost.native_captcha import private_native_captcha


async def upscale(profile: str, project: str, request_path: Path) -> None:
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    resolution = TargetResolution.from_cli(payload["resolution"])
    if resolution is not TargetResolution.RES_2K:
        raise ValueError("Explicit native CAPTCHA supports measured 2K upscale only")
    if type(payload.get("captchaRetry", 1)) is not int or payload.get("captchaRetry", 1) != 1:
        raise ValueError("Image upscale currently supports one explicit CAPTCHA attempt")
    settings = get_settings()
    out = request_path.parent
    with private_native_captcha(payload, project, "IMAGE_GENERATION"):
        async with FlowApiClient(
            profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
        ) as client:
            await client.upsample_image(
                media_id=payload["mediaGenerationId"],
                project_id=project,
                target_resolution=resolution,
                out_path=out / "upscaled.png",
            )


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(2)
    profile, project, request_path = sys.argv[1:]
    run_with_handlers(
        lambda: upscale(profile, project, Path(request_path)), cli_command="image upscale"
    )


if __name__ == "__main__":
    main()
