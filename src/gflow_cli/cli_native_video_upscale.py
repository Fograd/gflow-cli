"""Explicit native resolution promotion and target-specific model discovery."""

from __future__ import annotations

from pathlib import Path

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.native_video_upscale import NativeVideoUpscaleUnknownError
from gflow_cli.cli_native_captcha import native_captcha_option
from gflow_cli.selfhost.video_promotion_worker import run_promotion


@click.command("upscale-native")
@click.argument("media_id")
@click.option("--project", required=True)
@click.option("--resolution", type=click.Choice(["720p", "1080p", "4k"]), default="1080p")
@click.option(
    "--model-key", default=None, help="Fresh account-available promotion key; default lowest cost."
)
@click.option("--profile", default="default")
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("./out/promotions"))
@click.option("--json", "as_json", is_flag=True)
@native_captcha_option("VIDEO_GENERATION")
def upscale_native_command(
    media_id: str,
    project: str,
    resolution: str,
    model_key: str | None,
    profile: str,
    out_dir: Path,
    as_json: bool,
) -> None:
    """Generate a promoted video; may spend credits. Existing exports are separate."""
    resolved = _resolve_profile(profile)

    async def action() -> None:
        try:
            result = await run_promotion(
                resolved,
                project,
                {"mediaGenerationId": media_id, "resolution": resolution, "modelKey": model_key},
                out_dir,
            )
            if as_json:
                json_output.emit(result)
            else:
                click.echo(f"Saved promoted {resolution} video in {out_dir}")
        except NativeVideoUpscaleUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoUpscaleUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video upscale-native", as_json=as_json)


@click.command("upscale-models")
@click.option("--project", required=True)
@click.option("--resolution", type=click.Choice(["720p", "1080p", "4k"]), default="1080p")
@click.option("--profile", default="default")
@click.option("--json", "as_json", is_flag=True)
def upscale_models_command(project: str, resolution: str, profile: str, as_json: bool) -> None:
    """Read available promotion models, supported target and credit costs."""
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.native_video_upscale import list_native_promotion_models
    from gflow_cli.config import get_settings

    resolved = _resolve_profile(profile)

    async def action() -> None:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(resolved), headless=False
        ) as client:
            models = await list_native_promotion_models(client, project, resolution=resolution)
        if as_json:
            json_output.emit(
                {
                    "models": models,
                    "target_resolution": resolution,
                    "generationAcceptanceVerified": False,
                }
            )
        else:
            for item in models:
                click.echo(f"{item['model_key']} {item['credits']} credits")

    run_with_handlers(action, cli_command="video upscale-models", as_json=as_json)
