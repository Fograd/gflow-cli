"""Free promotion preflight: account discovery and checkpoint, no Google generation."""

import asyncio
import os
import shutil
import subprocess
from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api import native_video_upscale as promotion_module
from gflow_cli.api.client import FlowApiClient
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
def preflight(case, monkeypatch):
    mint = AsyncMock(return_value="synthetic-native-promotion-token-not-for-submission")
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", mint)
    build = promotion_module.promotion_args

    def capture(started, **kwargs):
        args = build(started, **kwargs)
        assert args[0][0][0] == [None, case["video"]]
        assert args[0][0][6] == 1 and kwargs["resolution"] == "720p"
        assert args[1][5] == case["RESOURCES_PROJECT"]
        case["request_prepared"] = True
        return args

    monkeypatch.setattr(promotion_module, "promotion_args", capture)

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
                chosen = "720p" if available["720p"] else None
                assert chosen is not None, "No account-available promotion model was observed"
                case["target"] = chosen
                with pytest.raises(PreflightCompleteError):
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
    assert case["request_prepared"] is True
    assert case["generation_requests"] == 0
    print("promotion_model_counts", case["model_counts"], "preflight_target", case["target"])


@given("an explicit existing owned native video promotion source", target_fixture="original_case")
def existing_configured(monkeypatch):
    import json
    from pathlib import Path

    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    source_file = os.getenv("GFLOW_CLI_E2E_PROMOTION_SOURCE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    if not home or profile not in {"pro2", "pro3"} or not source_file:
        pytest.skip("Explicit original owned promotion source opt-in required")
    source = json.loads(Path(source_file).read_text())["generated"]
    assert source.get("profile", profile) == profile
    source["profile"] = profile
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"source": source, "generation_requests": 0, "prepared": False}


@when("the original video is measured and promotion stops before real token mint")
def existing_preflight(original_case, monkeypatch):
    source = original_case["source"]
    build = promotion_module.promotion_args
    mint = AsyncMock(return_value="local-preflight-token-never-submitted")
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", mint)

    def capture(started, **kwargs):
        args = build(started, **kwargs)
        assert args[0][0][0] == [None, source["media_id"]]
        assert args[0][0][6] == 2 and kwargs["aspect"] == "9:16"
        original_case["prepared"] = True
        return args

    monkeypatch.setattr(promotion_module, "promotion_args", capture)

    async def checkpoint(started):
        assert started.source_media_id == source["media_id"]
        assert started.target_resolution == "1080p" and started.source_aspect == "9:16"
        raise PreflightCompleteError

    async def run():
        project = source["project_id"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(source["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                if "p0UkFb" in route.request.url or "p0UkFb" in (route.request.post_data or ""):
                    original_case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            try:
                measured = await promotion_module.read_promotion_source(
                    page, project_id=project, media_id=source["media_id"]
                )
                assert (measured.width, measured.height) == (720, 1280)
                original_case["dimensions"] = [measured.width, measured.height]
                await page.route("**/batchexecute*", guard)
                client._checkin_page(page)
                page = None
                with pytest.raises(PreflightCompleteError):
                    await upscale_native_video(
                        client,
                        project_id=project,
                        media_id=source["media_id"],
                        resolution="1080p",
                        on_started=checkpoint,
                    )
                page = await client._checkout_page()
                retained = await promotion_module.read_promotion_source(
                    page, project_id=project, media_id=source["media_id"]
                )
                assert retained.workflow_id == measured.workflow_id
            finally:
                if page is None:
                    page = await client._checkout_page()
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(run())
    assert mint.await_count == 1  # stub only; browser/provider mint never executed


@then("the exact source and target are prepared without generation or source mutation")
def existing_verify(original_case):
    assert original_case["prepared"] and original_case["generation_requests"] == 0
    print(
        "existing_promotion_source_dimensions",
        original_case["dimensions"],
        "real_mints",
        0,
        "submissions",
        0,
    )
