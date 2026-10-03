"""Private native video_edit worker: PROFILE PROJECT REQUEST_JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_extension import NativeExtensionStarted, new_extension_started
from gflow_cli.api.native_video_edit import (
    NativeVideoEditUnknownError,
    edit_native_video,
    video_edit_args,
    wait_native_video_edit,
)
from gflow_cli.config import get_settings
from gflow_cli.selfhost.extension_worker import write_started_checkpoint


async def generate(profile: str, project: str, request_path: Path) -> None:
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    out = request_path.parent
    json_output.emit(await run_edit(profile, project, payload, out))


async def run_edit(
    profile: str, project: str, payload: dict[str, Any], out: Path
) -> dict[str, Any]:
    # Reject malformed requests before creating the browser client.
    validation = new_extension_started(project, payload["referenceVideo_1"], 1)
    from gflow_cli.api.reference_markers import ReferenceSlot

    slot_ids = payload.get("referenceSlotIds")
    slots = (
        None
        if not slot_ids
        else {
            key: ReferenceSlot(
                "audio"
                if key.startswith("referenceAudio_")
                else "character"
                if key.startswith("character_")
                else "image",
                value,
            )
            for key, value in slot_ids.items()
        }
    )
    video_edit_args(
        validation,
        prompt=payload["prompt"],
        model_key=payload["modelKey"],
        aspect=payload.get("aspectRatio") or "16:9",
        token="validation",
        start_frame=payload.get("startFrameIndex_1", 0),
        end_frame=payload.get("endFrameIndex_1", 240),
        image_ids=tuple(payload.get("imageMediaIds", [])),
        audio_ids=tuple(payload.get("audioMediaIds", [])),
        character_ids=tuple(payload.get("characterMediaIds", [])),
        reference_slots=slots,
    )
    out.mkdir(parents=True, exist_ok=True)

    async def checkpoint(started: NativeExtensionStarted) -> None:
        write_started_checkpoint(out / "video_edit-started.json", started)

    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(profile), headless=False
    ) as client:
        started = await edit_native_video(
            client,
            project_id=project,
            media_id=payload["referenceVideo_1"],
            prompt=payload["prompt"],
            model_key=payload["modelKey"],
            start_frame=payload.get("startFrameIndex_1", 0),
            end_frame=payload.get("endFrameIndex_1"),
            image_ids=tuple(payload.get("imageMediaIds", [])),
            audio_ids=tuple(payload.get("audioMediaIds", [])),
            character_ids=tuple(payload.get("characterMediaIds", [])),
            reference_slot_ids=slot_ids,
            on_started=checkpoint,
        )
        records = await wait_native_video_edit(client, started)
        outputs: list[dict[str, Any]] = []
        for record in records:
            path = out / f"{record.media_id}.mp4"
            if record.video_url is None:
                raise NativeVideoEditUnknownError(started)
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
            "type": "video_edit_result",
            "project_id": project,
            "source_media_id": started.source_media_id,
            "startFrameIndex": started.start_frame,
            "endFrameIndex": started.end_frame,
            "sourceDurationSeconds": started.source_duration_seconds,
            "results": outputs,
        }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: video_edit_worker PROFILE PROJECT REQUEST_JSON")
    profile, project, request = sys.argv[1:]

    async def action() -> None:
        try:
            await generate(profile, project, Path(request))
        except NativeVideoEditUnknownError as error:
            json_output.emit(
                {
                    "type": "error",
                    "error_class": "NativeVideoEditUnknownError",
                    "error": error.to_problem_details(),
                }
            )
            raise SystemExit(40) from None

    run_with_handlers(action, cli_command="video extend-native", as_json=True)


if __name__ == "__main__":
    main()
