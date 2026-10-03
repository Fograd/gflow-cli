"""Private native reference-video worker: PROFILE PROJECT REQUEST_JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_reference_video import (
    NativeReferenceVideoStarted,
    generate_native_reference_video,
    new_reference_started,
    reference_args,
    wait_native_reference_video,
)
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError, NativeVideoGenerationUnknownError


async def run_reference_video(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    images = tuple(payload.get("referenceImageIds", ()))
    audio = tuple(payload.get("referenceAudioIds", ()))
    preflight = new_reference_started(project, payload.get("count", 1))
    reference_args(
        preflight,
        prompt=payload["prompt"],
        image_ids=images,
        audio_ids=audio,
        model_key=payload.get("modelKey") or "discovery",
        aspect=payload.get("aspectRatio", "16:9"),
        resolution=payload.get("resolution", "720p"),
        token="validation",
    )
    duration = payload.get("duration")
    if duration is not None and (type(duration) is not int or not 1 <= duration <= 60):
        raise ConfigurationError(detail="Native video duration requires a bounded integer")
    out.mkdir(parents=True, exist_ok=True)

    async def checkpoint(started: NativeReferenceVideoStarted) -> None:
        path = out / "reference-video-started.json"
        path.write_text(
            json.dumps(
                {
                    "project_id": started.project_id,
                    "media_ids": started.media_ids,
                    "workflow_ids": started.workflow_ids,
                }
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)

    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(profile), headless=False
    ) as client:
        started = await generate_native_reference_video(
            client,
            project_id=project,
            prompt=payload["prompt"],
            reference_image_ids=images,
            reference_audio_ids=audio,
            model_key=payload.get("modelKey"),
            count=payload.get("count", 1),
            aspect=payload.get("aspectRatio", "16:9"),
            duration=payload.get("duration"),
            resolution=payload.get("resolution", "720p"),
            on_started=checkpoint,
        )
        records = await wait_native_reference_video(
            client, started, timeout_s=payload.get("timeout", 600)
        )
        outputs: list[dict[str, Any]] = []
        for record in records:
            path = out / f"{record.media_id}.mp4"
            if record.video_url is None:
                raise NativeVideoGenerationUnknownError(
                    project_id=project,
                    media_ids=started.media_ids,
                    workflow_ids=started.workflow_ids,
                    phase="video_poll",
                )
            try:
                await client.download(record.video_url, path)
            except Exception:
                raise NativeVideoGenerationUnknownError(
                    project_id=project,
                    media_ids=started.media_ids,
                    workflow_ids=started.workflow_ids,
                    phase="video_poll",
                ) from None
            outputs.append(
                {
                    "media_name": record.media_id,
                    "media_id": record.media_id,
                    "workflow_id": record.workflow_id,
                    "local_path": str(path),
                }
            )
        return {"type": "video_reference_result", "project_id": project, "results": outputs}


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: reference_video_worker PROFILE PROJECT REQUEST_JSON")
    profile, project, request = sys.argv[1:]

    async def action() -> None:
        path = Path(request)
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            json_output.emit(await run_reference_video(profile, project, payload, path.parent))
        except NativeVideoGenerationUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoGenerationUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video reference-native", as_json=True)


if __name__ == "__main__":
    main()
