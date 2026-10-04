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
from gflow_cli.errors import (
    ConfigurationError,
    ContentPolicyError,
    NativeQuotaError,
    NativeUIVideoBatchUnknownError,
    WafRejectionError,
)
from gflow_cli.selfhost.config import environment_root
from gflow_cli.selfhost.video_captcha_policy import run_with_video_captcha_policy
from gflow_cli.worker.codec import build_video_request


def _checkpoint(out: Path, project: str, media: list[str], workflows: list[str]) -> None:
    path = out / "video-checkpoint.json"
    temporary = out / "video-checkpoint.tmp"
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(
            {
                "project_id": project,
                "media_ids": media,
                "workflow_ids": workflows,
                "phase": "video_poll" if media else "video_submit",
            },
            file,
        )
    temporary.replace(path)


async def generate_payload(profile: str, project: str, out: Path, payload: dict[str, Any]) -> None:
    if "seed" in payload:
        raise ValueError("Numeric video seed has no verified generic wire support")
    if (
        any(payload.get(key) is not None for key in ("captchaOrder", "captchaRetry"))
        and active_video_overrides.get() is None
    ):
        raise ConfigurationError(detail="Explicit video provider policy is not installed")
    refs = payload.get("reference_paths", [])
    request_payload = {
        key: value
        for key, value in payload.items()
        if key
        not in (
            "captchaSecret",
            "captchaOrder",
            "captchaRetry",
            "captcha_token",
            "captcha_token_file",
            "captchaToken",
        )
    }
    request = build_video_request(
        {
            **request_payload,
            "aspect": payload["aspectRatio"],
            "mode": "i2v" if payload.get("start_image") else "r2v" if refs else "t2v",
            "reference_images": refs,
        }
    )
    if request.count > 1:
        media: list[str] = []
        workflows: list[str] = []

        async def batch_started(value: VideoStarted) -> None:
            if value.media_id not in media:
                media.append(value.media_id)
                if value.workflow_id is not None:
                    workflows.append(value.workflow_id)
            _checkpoint(out, project, media, workflows)

        def batch_checkpoint(value: Any) -> None:
            if value.phase == "submit_attempted":
                _checkpoint(out, project, [], [])

        try:
            settings = get_settings()
            async with FlowApiClient(
                profile_dir=_make_provider_dir(profile), headless=settings.headless, out_dir=out
            ) as client:
                result = await client.generate_videos_batch(
                    req=request,
                    project_id=project,
                    out_dir=out,
                    download=True,
                    on_started=batch_started,
                    on_checkpoint=batch_checkpoint,
                )
                output = json_output.video_batch_result(
                    command="selfhost videos", request=request, result=result
                )
                override = active_video_overrides.get()
                if override is not None:
                    output["captchaProvider"] = override.provider_name or "supplied"
                json_output.emit(output)
        except NativeUIVideoBatchUnknownError as exc:
            _checkpoint(out, project, list(exc.media_ids), list(exc.workflow_ids))
            json_output.emit(
                {
                    "error": {
                        "class": "GeneralVideoOutcomeUnknown",
                        "project_id": project,
                        "media_ids": list(exc.media_ids),
                        "workflow_ids": list(exc.workflow_ids),
                        "outcome_unknown": True,
                        "phase": exc.phase,
                    }
                }
            )
            raise SystemExit(40) from None
        return

    context = copy_context()

    async def token(page: Any) -> str:
        value = context.run(take_native_captcha_token, str(page.url), "VIDEO_GENERATION")
        if value is None:
            raise ConfigurationError(detail="Private video CAPTCHA token is unavailable")
        return value

    override = active_video_overrides.get() or VideoOverrides(
        project=project, count=payload["count"], token=token
    )
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
            from gflow_cli.services.video_captcha import require_native_video_captcha_host

            require_native_video_captcha_host(client, active=True)
            result = await client.generate_video(
                req=request, project_id=project, out_dir=out, download=True, on_started=started
            )
            output = json_output.video_result(
                command="selfhost videos", request=request, result=result
            )
            # Actual selected provider is added by the owning explicit policy wrapper.
            output["captchaProvider"] = override.provider_name or "supplied"
            json_output.emit(output)
    except Exception as exc:
        if isinstance(exc, (ContentPolicyError, WafRejectionError, NativeQuotaError)) and (
            not override.dispatched
            or (override.terminal == "rejected" and not override.known_media_ids)
        ):
            raise
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

    async def attempt(override: VideoOverrides | None) -> None:
        await generate_payload(profile, project, job_path.parent, payload)

    await run_with_video_captcha_policy(payload, project, environment_root(), attempt)


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
