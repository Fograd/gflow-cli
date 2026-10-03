"""Free promotion preflight: account discovery and checkpoint, no Google generation."""

import asyncio
import os
import shutil
import subprocess

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_captcha import native_captcha_token
from gflow_cli.api.native_video_upscale import list_native_promotion_models, upscale_native_video
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.migrated_video_upload import upload_video
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_video_promotion.feature")


class PreflightCompleteError(Exception):
    pass


@given("an explicit native account and free video promotion fixture", target_fixture="case")
def configured(monkeypatch, tmp_path):
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_NATIVE_PROMOTION") != "1":
        pytest.skip("Explicit private free promotion preflight opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    if not shutil.which("ffmpeg"):
        pytest.skip("Free fixture needs ffmpeg")
    path = tmp_path / "promotion-source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=cyan:s=640x360:r=24:d=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        timeout=15,
    )
    return {**values, "path": path, "boundaries": 0, "generation_requests": 0}


@when("promotion model discovery and a supported target reach the checkpoint")
def preflight(case):
    async def checkpoint(started):
        case["boundaries"] += 1
        assert started.source_media_id == case["video"]
        assert len(started.media_ids) == 1 and started.workflow_ids == (started.source_workflow_id,)
        raise PreflightCompleteError

    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                if any(
                    rpc in route.request.url or rpc in (route.request.post_data or "")
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "YhhmEf",
                        "eb1hJf",
                        "p0UkFb",
                    )
                ):
                    case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            video = None
            originals = None
            try:
                originals = {
                    x["media_id"]
                    for x in project_media(await read_project_payload(page, project), project)
                    if not x["archived"]
                }
                video, _ = await upload_video(page, project, case["path"], rights_confirmed=True)
                case["video"] = video
                client._checkin_page(page)
                page = None
                available = {}
                for target in ("720p", "1080p", "4k"):
                    available[target] = await list_native_promotion_models(
                        client, project, resolution=target
                    )
                case["model_counts"] = {key: len(value) for key, value in available.items()}
                chosen = next((target for target, rows in available.items() if rows), None)
                assert chosen is not None, "No account-available promotion model was observed"
                case["target"] = chosen
                with (
                    native_captcha_token(
                        "synthetic-native-promotion-token-not-for-submission",
                        project_id=project,
                        action="VIDEO_GENERATION",
                    ),
                    pytest.raises(PreflightCompleteError),
                ):
                    await upscale_native_video(
                        client,
                        project_id=project,
                        media_id=video,
                        resolution=chosen,
                        on_started=checkpoint,
                    )
            finally:
                if page is None:
                    page = await client._checkout_page()
                if video:
                    assert await trash_media(page, project, [video]) == [video]
                if originals is not None:
                    assert originals <= {
                        x["media_id"]
                        for x in project_media(await read_project_payload(page, project), project)
                        if not x["archived"]
                    }
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(run())


@then("promotion stops before dispatch and only its free fixture is archived")
def verify(case):
    assert case["boundaries"] == 1
    assert case["generation_requests"] == 0
    print("promotion_model_counts", case["model_counts"], "preflight_target", case["target"])
