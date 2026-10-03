"""Native video from already-owned image/audio ingredients."""

from __future__ import annotations

from pathlib import Path

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.errors import NativeVideoGenerationUnknownError
from gflow_cli.selfhost.reference_video_worker import run_reference_video


@click.command("reference-native")
@click.option("--project", required=True)
@click.option("--prompt", required=True)
@click.option("--image-ref", multiple=True, help="Owned image UUID; repeat up to seven times.")
@click.option("--audio-ref", multiple=True, help="Owned audio UUID; repeat up to five times.")
@click.option(
    "--character-ref", multiple=True, help="Owned character UUID; native combined limits apply."
)
@click.option(
    "--model-key", default=None, help="Discovered native key; default selects available Omni Flash."
)
@click.option("--count", type=click.IntRange(1, 4), default=1)
@click.option("--aspect", type=click.Choice(["16:9", "9:16", "1:1"]), default="16:9")
@click.option("--duration", type=click.IntRange(1, 60), default=None)
@click.option("--resolution", type=click.Choice(["360p", "720p", "1080p", "4k"]), default="720p")
@click.option("--profile", default="default")
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("./out/reference-video"))
@click.option("--json", "as_json", is_flag=True)
def reference_native_command(
    project: str,
    prompt: str,
    image_ref: tuple[str, ...],
    audio_ref: tuple[str, ...],
    character_ref: tuple[str, ...],
    model_key: str | None,
    count: int,
    aspect: str,
    duration: int | None,
    resolution: str,
    profile: str,
    out_dir: Path,
    as_json: bool,
) -> None:
    """Generate once from UUID ingredients; download independently identified outputs."""
    profile = _resolve_profile(profile)
    payload = {
        "prompt": prompt,
        "referenceImageIds": image_ref,
        "referenceAudioIds": audio_ref,
        "referenceCharacterIds": character_ref,
        "modelKey": model_key,
        "count": count,
        "aspectRatio": aspect,
        "duration": duration,
        "resolution": resolution,
    }

    async def action() -> None:
        try:
            result = await run_reference_video(profile, project, payload, out_dir)
            if as_json:
                json_output.emit(result)
            else:
                click.echo(f"Saved {len(result['results'])} reference video(s) in {out_dir}")
        except NativeVideoGenerationUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoGenerationUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video reference-native", as_json=as_json)


@click.command("reference-models")
@click.option("--project", required=True)
@click.option("--with-audio", is_flag=True)
@click.option("--profile", default="default")
@click.option("--json", "as_json", is_flag=True)
def reference_models_command(project: str, with_audio: bool, profile: str, as_json: bool) -> None:
    """Discover tier-available image/audio-reference model keys."""
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.config import get_settings

    profile = _resolve_profile(profile)

    async def action() -> None:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(profile), headless=False
        ) as client:
            models = await client.list_native_reference_video_models(project, with_audio=with_audio)
        if as_json:
            json_output.emit(
                {
                    "models": models,
                    "source": "native-flow-getmodels",
                    "generationAcceptanceVerified": False,
                }
            )
        else:
            for row in models:
                click.echo(f"{row['model_key']}  {row['credits']} credits")

    run_with_handlers(action, cli_command="video reference-models", as_json=as_json)
