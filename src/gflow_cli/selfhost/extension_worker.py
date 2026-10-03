"""Private native extension worker: PROFILE PROJECT REQUEST_JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_extension import (
    NativeExtensionStarted,
    NativeExtensionUnknownError,
    extend_native_video,
    extension_args,
    new_extension_started,
    wait_native_extension,
)
from gflow_cli.config import get_settings


def write_started_checkpoint(path: Path, started: NativeExtensionStarted) -> None:
    """Persist source and assigned output identities in the private worker journal."""
    path.write_text(
        json.dumps(
            {
                "project_id": started.project_id,
                "source_media_id": started.source_media_id,
                "media_ids": list(started.media_ids),
                "workflow_ids": list(started.workflow_ids),
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


async def generate(profile: str, project: str, request_path: Path) -> None:
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    out = request_path.parent
    json_output.emit(await run_extension(profile, project, payload, out))


async def run_extension(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    from gflow_cli.selfhost.native_captcha import private_native_captcha

    with private_native_captcha(payload, project, "VIDEO_GENERATION"):
        return await _run_extension(profile, project, payload, out)


async def _run_extension(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    # Reject malformed requests before creating the browser client.
    validation = new_extension_started(
        project, payload["mediaGenerationId"], payload.get("count", 1)
    )
    extension_args(
        validation,
        prompt=payload["prompt"],
        model_key=payload.get("modelKey") or "select-native-model",
        aspect=payload.get("aspectRatio") or "16:9",
        token="validation",
        trim_start_frame=payload.get("trimStartFrame"),
        trim_end_frame=payload.get("trimEndFrame"),
    )
    out.mkdir(parents=True, exist_ok=True)

    async def checkpoint(started: NativeExtensionStarted) -> None:
        write_started_checkpoint(out / "extension-started.json", started)

    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(profile), headless=False
    ) as client:
        started = await extend_native_video(
            client,
            project_id=project,
            media_id=payload["mediaGenerationId"],
            prompt=payload["prompt"],
            model_key=payload.get("modelKey"),
            count=payload.get("count", 1),
            aspect=payload.get("aspectRatio"),
            trim_start_frame=payload.get("trimStartFrame"),
            trim_end_frame=payload.get("trimEndFrame"),
            on_started=checkpoint,
        )
        records = await wait_native_extension(
            client, started, timeout_s=payload.get("timeout", 600)
        )
        outputs: list[dict[str, Any]] = []
        for record in records:
            path = out / f"{record.media_id}.mp4"
            if record.video_url is None:
                raise NativeExtensionUnknownError(started)
            await client.download(record.video_url, path)
            outputs.append(
                {
                    "media_name": record.media_id,
                    "media_id": record.media_id,
                    "workflow_id": record.workflow_id,
                    "local_path": str(path),
                }
            )
        return {
            "type": "video_extension_result",
            "project_id": project,
            "source_media_id": started.source_media_id,
            "results": outputs,
        }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: extension_worker PROFILE PROJECT REQUEST_JSON")
    profile, project, request = sys.argv[1:]

    async def action() -> None:
        try:
            await generate(profile, project, Path(request))
        except NativeExtensionUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeExtensionUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video extend-native", as_json=True)


if __name__ == "__main__":
    main()
