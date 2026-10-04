"""Private supplied-CAPTCHA generic UI video worker; no token on argv or JSON."""

from __future__ import annotations

import json
import os
import sys
from contextvars import copy_context
from pathlib import Path
from typing import Any

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_captcha import take_native_captcha_token
from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides, active_video_overrides
from gflow_cli.api.video import VideoStarted
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError, ContentPolicyError, WafRejectionError
from gflow_cli.selfhost.native_captcha import private_native_captcha
from gflow_cli.worker.codec import build_video_request


def _checkpoint(out: Path, project: str, media: list[str], workflows: list[str]) -> None:
    path = out / "video-checkpoint.json"
    temporary = out / "video-checkpoint.tmp"
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump({"project_id": project, "media_ids": media, "workflow_ids": workflows}, file)
    temporary.replace(path)


async def generate_payload(profile: str, project: str, out: Path, payload: dict[str, Any]) -> None:
    if "seed" in payload:
        raise ValueError("Numeric video seed has no verified generic wire support")
    if payload.get("captchaOrder") or payload.get("captchaRetry"):
        raise ValueError("Generic video provider CAPTCHA controls are not yet supported")
    refs = payload.get("reference_paths", [])
    request = build_video_request(
        {
            **payload,
            "aspect": payload["aspectRatio"],
            "mode": "i2v" if payload.get("start_image") else "r2v" if refs else "t2v",
            "reference_images": refs,
        }
    )
    context = copy_context()

    async def token(page: Any) -> str:
        value = context.run(take_native_captcha_token, str(page.url), "VIDEO_GENERATION")
        if value is None:
            raise ConfigurationError(detail="Private video CAPTCHA token is unavailable")
        return value

    override = VideoOverrides(project=project, count=payload["count"], token=token)
    state = active_video_overrides.set(override)
    media: list[str] = []
    workflows: list[str] = []

    async def started(value: VideoStarted) -> None:
        media[:] = [value.media_id]
        workflows[:] = [value.workflow_id] if value.workflow_id else []
        _checkpoint(out, project, media, workflows)

    try:
        settings = get_settings()
        async with FlowApiClient(
            profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
        ) as client:
            result = await client.generate_video(
                req=request, project_id=project, out_dir=out, download=True, on_started=started
            )
            output = json_output.video_result(
                command="selfhost videos", request=request, result=result
            )
            output["captchaProvider"] = "supplied"
            json_output.emit(output)
    except (ContentPolicyError, WafRejectionError):
        raise
    except Exception:
        if override.dispatched:
            media[:] = list(dict.fromkeys(media + override.known_media_ids))[:4]
            workflows[:] = list(dict.fromkeys(workflows + override.known_workflow_ids))[:4]
            _checkpoint(out, project, media, workflows)
            json_output.emit(
                {
                    "error": {
                        "class": "GeneralVideoOutcomeUnknown",
                        "project_id": project,
                        "media_ids": media,
                        "workflow_ids": workflows,
                        "outcome_unknown": True,
                        "phase": "video_poll" if media else "video_submit",
                    }
                }
            )
            raise SystemExit(40) from None
        raise
    finally:
        override.close()
        active_video_overrides.reset(state)


async def generate(profile: str, project: str, job_path: Path) -> None:
    payload: dict[str, Any] = json.loads(job_path.read_text(encoding="utf-8"))
    with private_native_captcha(payload, project, "VIDEO_GENERATION"):
        await generate_payload(profile, project, job_path.parent, payload)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(2)
    profile, project, job_path = sys.argv[1:]
    run_with_handlers(
        lambda: generate(profile, project, Path(job_path)),
        cli_command="selfhost videos",
        as_json=True,
    )


if __name__ == "__main__":
    main()
