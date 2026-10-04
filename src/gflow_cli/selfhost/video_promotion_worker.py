"""Private native video promotion worker: PROFILE PROJECT REQUEST_JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_video_upscale import (
    TARGETS,
    NativePromotionStarted,
    NativeVideoUpscaleUnknownError,
    upscale_native_video,
    wait_native_promotion,
)
from gflow_cli.api.transports.native_asset_download import download_asset
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.extension_worker import write_started_checkpoint
from gflow_cli.selfhost.native_captcha_policy import run_with_native_captcha_policy


async def run_promotion(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    if payload.get("resolution", "1080p") not in TARGETS:
        raise ConfigurationError(detail="Native promotion target must be720p,1080p or4k")
    return await run_with_native_captcha_policy(
        payload,
        project,
        "VIDEO_GENERATION",
        lambda: _run_promotion(profile, project, payload, out),
    )


async def _run_promotion(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(profile), headless=False
    ) as client:
        out.mkdir(parents=True, exist_ok=True)

        async def checkpoint(started: NativePromotionStarted) -> None:
            write_started_checkpoint(out / "promotion-started.json", started)

        started = await upscale_native_video(
            client,
            project_id=project,
            media_id=payload["mediaGenerationId"],
            resolution=payload.get("resolution", "1080p"),
            model_key=payload.get("modelKey"),
            on_started=checkpoint,
        )
        await wait_native_promotion(client, started, timeout_s=payload.get("timeout", 600))
        media = started.media_ids[0]
        try:
            asset = await client.get_native_asset(project, media)
            pixels = {"720p": 720, "1080p": 1080, "4k": 2160}[started.target_resolution]
            if (
                asset.kind != "video"
                or asset.workflow_id != started.source_workflow_id
                or asset.width is None
                or asset.height is None
                or min(asset.width, asset.height) != pixels
            ):
                raise NativeVideoUpscaleUnknownError(started)
            downloaded = await download_asset(asset, out)
        except NativeVideoUpscaleUnknownError:
            raise
        except Exception:
            raise NativeVideoUpscaleUnknownError(started) from None
        return {
            "type": "video_promotion_result",
            "project_id": project,
            "source_media_id": started.source_media_id,
            "target_resolution": started.target_resolution,
            "results": [
                {
                    "media_id": media,
                    "workflow_id": asset.workflow_id,
                    "local_path": str(downloaded.path),
                    "width": asset.width,
                    "height": asset.height,
                }
            ],
        }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: video_promotion_worker PROFILE PROJECT REQUEST_JSON")
    profile, project, path = sys.argv[1:]

    async def action() -> None:
        try:
            payload = json.loads(Path(path).read_text())
            json_output.emit(await run_promotion(profile, project, payload, Path(path).parent))
        except NativeVideoUpscaleUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoUpscaleUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video upscale-native", as_json=True)


if __name__ == "__main__":
    main()
