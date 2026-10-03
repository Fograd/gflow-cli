"""Standalone native extension command; legacy scene extension remains separate."""

from __future__ import annotations

from pathlib import Path

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.native_extension import NativeExtensionUnknownError
from gflow_cli.cli_native_captcha import native_captcha_option
from gflow_cli.selfhost.extension_worker import run_extension


@click.command("extend-native")
@click.argument("media_id")
@click.option("--project", required=True)
@click.option("--prompt", required=True)
@click.option(
    "--model-key",
    default=None,
    help="Native key; default selects lowest-cost available extension model.",
)
@click.option("--count", type=click.IntRange(1, 4), default=1)
@click.option("--aspect", type=click.Choice(["16:9", "9:16", "1:1"]), default=None)
@click.option("--trim-start-frame", type=click.IntRange(min=0), default=None)
@click.option("--trim-end-frame", type=click.IntRange(min=0), default=None)
@click.option("--profile", default="default")
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("./out/extensions"))
@click.option("--json", "as_json", is_flag=True)
@native_captcha_option("VIDEO_GENERATION")
def extend_native_command(
    media_id: str,
    project: str,
    prompt: str,
    model_key: str | None,
    count: int,
    aspect: str | None,
    trim_start_frame: int | None,
    trim_end_frame: int | None,
    profile: str,
    out_dir: Path,
    as_json: bool,
) -> None:
    """Extend once; download only the independently identified extension outputs."""
    profile = _resolve_profile(profile)
    payload = {
        "mediaGenerationId": media_id,
        "prompt": prompt,
        "modelKey": model_key,
        "count": count,
        "aspectRatio": aspect,
        "trimStartFrame": trim_start_frame,
        "trimEndFrame": trim_end_frame,
    }

    async def action() -> None:
        try:
            result = await run_extension(profile, project, payload, out_dir)
            if as_json:
                json_output.emit(result)
            else:
                click.echo(f"Saved {len(result['results'])} standalone extension(s) in {out_dir}")
        except NativeExtensionUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeExtensionUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video extend-native", as_json=as_json)


@click.command("extension-models")
@click.option("--project", required=True)
@click.option("--profile", default="default")
@click.option("--json", "as_json", is_flag=True)
def extension_models_command(project: str, profile: str, as_json: bool) -> None:
    """List current tier-available native extension model keys and credit costs."""
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.native_extension import list_native_extension_models
    from gflow_cli.config import get_settings

    resolved = _resolve_profile(profile)

    async def action() -> None:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(resolved), headless=False
        ) as client:
            models = await list_native_extension_models(client, project)
        if as_json:
            json_output.emit(
                {
                    "models": models,
                    "source": "native-flow-getmodels",
                    "generationAcceptanceVerified": False,
                }
            )
        else:
            for model in models:
                click.echo(f"{model['model_key']}  {model['credits']} credits")

    run_with_handlers(action, cli_command="video extension-models", as_json=as_json)
