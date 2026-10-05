"""Standalone source-derived Omni edit command."""

from __future__ import annotations

import json
from pathlib import Path

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_extension import NativeExtensionStarted
from gflow_cli.api.native_video_edit import (
    NativeVideoEditUnknownError,
    edit_native_video,
    wait_native_video_edit,
)
from gflow_cli.api.native_video_prompt import parse_video_slot_options, video_slot_inputs
from gflow_cli.cli_native_captcha import native_captcha_option
from gflow_cli.config import get_settings
from gflow_cli.services.native_captcha import (
    native_captcha_client,
    native_captcha_controls,
    run_native_captcha_with_controls,
)


@click.command("edit-native")
@click.argument("media_id")
@click.option("--project", required=True)
@click.option("--prompt", required=True)
@click.option("--model-key", required=True, help="Explicit account-native Omni edit model key.")
@click.option("--start-frame", type=click.IntRange(0, 239), default=0)
@click.option(
    "--end-frame",
    type=click.IntRange(1, 240),
    default=None,
    help="Default: floor(source seconds ×24), capped240.",
)
@click.option("--image-ref", multiple=True, help="Same-project existing image UUID; up to5.")
@click.option(
    "--audio-ref", multiple=True, help="Owned native audio UUID or available system preset; up to3."
)
@click.option(
    "--character-ref", multiple=True, help="Owned character UUID; combined native limits apply."
)
@click.option(
    "--reference-slot",
    "reference_slot_ids",
    multiple=True,
    help="Explicit SLOT=REFERENCE, e.g. referenceImage_3=UUID; replaces reference lists.",
)
@click.option("--profile", default=None)
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("./out/edits"))
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--captcha-order", default=None, help="Explicit unique provider order: CapSolver,2Captcha."
)
@click.option(
    "--captcha-retry",
    type=click.IntRange(1, 10),
    default=None,
    help="Total confirmed-WAF attempts; explicit use selects providers. Omitted: browser once.",
)
@native_captcha_option("VIDEO_GENERATION")
def edit_native_command(
    media_id: str,
    project: str,
    prompt: str,
    model_key: str,
    start_frame: int,
    end_frame: int | None,
    image_ref: tuple[str, ...],
    audio_ref: tuple[str, ...],
    character_ref: tuple[str, ...],
    profile: str | None,
    out_dir: Path,
    as_json: bool,
    reference_slot_ids: tuple[str, ...] = (),
    captcha_order: str | None = None,
    captcha_retry: int | None = None,
) -> None:
    """Edit one owned video slice; output duration follows the frame window."""
    native_captcha_controls(captcha_order=captcha_order, captcha_retry=captcha_retry)
    slots = parse_video_slot_options(reference_slot_ids)
    image_ref, audio_ref, character_ref, _ = video_slot_inputs(
        prompt, image_ref, audio_ref, character_ref, slots
    )
    selected = _resolve_profile(profile)

    async def action() -> None:
        out_dir.mkdir(parents=True, exist_ok=True)

        async def checkpoint(started: NativeExtensionStarted) -> None:
            path = out_dir / "edit-started.json"
            path.write_text(
                json.dumps(
                    {
                        "project_id": started.project_id,
                        "source_media_id": started.source_media_id,
                        "media_ids": started.media_ids,
                        "workflow_ids": started.workflow_ids,
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)

        try:

            async def attempt() -> dict[str, object]:
                async with native_captcha_client(
                    FlowApiClient(
                        profile_dir=get_settings().profile_subdir(selected), headless=False
                    ),
                    active=captcha_order is not None or captcha_retry is not None,
                ) as client:
                    started = await edit_native_video(
                        client,
                        project_id=project,
                        media_id=media_id,
                        prompt=prompt,
                        model_key=model_key,
                        start_frame=start_frame,
                        end_frame=end_frame,
                        image_ids=image_ref,
                        audio_ids=audio_ref,
                        character_ids=character_ref,
                        reference_slot_ids=slots,
                        on_started=checkpoint,
                    )
                    records = await wait_native_video_edit(client, started)
                    outputs: list[dict[str, str]] = []
                    for record in records:
                        if record.video_url is None:
                            raise NativeVideoEditUnknownError(started)
                        path = out_dir / f"{record.media_id}.mp4"
                        await client.download(record.video_url, path)
                        outputs.append(
                            {
                                "media_id": record.media_id,
                                "workflow_id": record.workflow_id,
                                "local_path": str(path),
                            }
                        )
                    return {
                        "type": "video_edit_result",
                        "project_id": project,
                        "source_media_id": media_id,
                        "startFrameIndex": started.start_frame,
                        "endFrameIndex": started.end_frame,
                        "sourceDurationSeconds": started.source_duration_seconds,
                        "results": outputs,
                    }

            result = await run_native_captcha_with_controls(
                project_id=project,
                action="VIDEO_GENERATION",
                attempt=attempt,
                captcha_order=captcha_order,
                captcha_retry=captcha_retry,
            )
            if as_json:
                json_output.emit(result)
            else:
                click.echo(f"Saved one edited clip in {out_dir}")
        except NativeVideoEditUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoEditUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise click.exceptions.Exit(40) from None

    run_with_handlers(action, cli_command="video edit-native", as_json=as_json)


@click.command("edit-models")
@click.option("--project", required=True)
@click.option("--profile", default=None)
def edit_models_command(project: str, profile: str | None) -> None:
    """Read available account-native edit model keys and credit metadata."""
    selected = _resolve_profile(profile)

    async def action() -> None:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(selected), headless=False
        ) as client:
            json_output.emit(
                {
                    "type": "video_edit_models",
                    "models": await client.list_native_video_edit_models(project),
                }
            )

    run_with_handlers(action, cli_command="video edit-models", as_json=True)
