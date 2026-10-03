"""Free-fixture supplied native token interception; no Google generation."""

import asyncio
import os
import shutil
import subprocess

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_captcha import native_captcha_token
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_extension import _read_native, parse_extension_models
from gflow_cli.api.native_video_audio import normalize_audio_reference
from gflow_cli.api.native_video_characters import model_reference_limits, reference_capacity
from gflow_cli.api.transports.migrated_catalog import parse_native_voices
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.migrated_video_upload import upload_video
from gflow_cli.api.transports.native_voices import _mint_audio_token
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_captcha.feature")


class PreflightCompleteError(Exception):
    pass


@given(
    "an explicit native profile and free fixture for supplied token preflight",
    target_fixture="case",
)
def configured(monkeypatch, tmp_path):
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_NATIVE_CAPTCHA") != "1":
        pytest.skip("Explicit private read-only preset preflight opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    if not shutil.which("ffmpeg"):
        pytest.skip("Free video fixture requires ffmpeg")
    path = tmp_path / "preset-audio-source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=cyan:s=256x144:r=24:d=1",
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
    return {"path": path, **values, "boundaries": 0, "generation_requests": 0}


@when("native supplied token scopes reach reference edit checkpoints and audio mint")
def preflight(case, monkeypatch):
    token = "synthetic-private-native-token-not-for-submission"

    async def stop_before_dispatch(started):
        case["boundaries"] += 1
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

            video = None
            originals = None
            await page.route("**/batchexecute*", guard)
            try:
                payload = await read_project_payload(page, project)
                voices = parse_native_voices(payload)
                assert any(row["voice"].lower() == "charon" for row in voices)
                assert normalize_audio_reference("voices/charon") == "Charon"
                active = {
                    row["media_id"]
                    for row in project_media(payload, project)
                    if not row["archived"]
                }
                originals = active
                video, _ = await upload_video(page, project, case["path"], rights_confirmed=True)
                for _ in range(10):
                    payload = await read_project_payload(page, project)
                    matches = [
                        row
                        for row in parse_media_snapshot(payload, project)["media"]
                        if row["media_id"] == video and row["kind"] == "video"
                    ]
                    if matches:
                        break
                    await asyncio.sleep(0.5)
                assert matches
                source = matches[0]
                models = await _read_native(page, "HTrJv", [], project)
                credits = await _read_native(page, "nzlxg", [], project)
                options = parse_extension_models(
                    models, tier=credits[3], required_requirements=(1, 6, 20)
                )
                eligible = [
                    row
                    for row in options
                    if reference_capacity(
                        0, 1, {}, model_reference_limits(models, row["model_key"])
                    )
                ]
                assert eligible, "No observed edit model supports one explicit audio preset"
                key = min(eligible, key=lambda row: row["credits"])["model_key"]
                with native_captcha_token(token, project_id=project, action="AUDIO_GENERATION"):
                    assert await _mint_audio_token(page) == token
                    case["boundaries"] += 1
                client._checkin_page(page)
                page = None
                with (
                    native_captcha_token(token, project_id=project, action="VIDEO_GENERATION"),
                    pytest.raises(PreflightCompleteError),
                ):
                    await client.generate_native_reference_video(
                        project_id=project,
                        prompt="Use @referenceAudio_3",
                        reference_audio_ids=("voices/charon",),
                        reference_slot_ids={"referenceAudio_3": "voices/charon"},
                        on_started=stop_before_dispatch,
                    )
                with (
                    native_captcha_token(token, project_id=project, action="VIDEO_GENERATION"),
                    pytest.raises(PreflightCompleteError),
                ):
                    await client.edit_native_video(
                        project_id=project,
                        media_id=source["media_id"],
                        prompt="Use @referenceAudio_3",
                        model_key=key,
                        audio_ids=("voices/charon",),
                        reference_slot_ids={"referenceAudio_3": "voices/charon"},
                        on_started=stop_before_dispatch,
                        end_frame=24,
                    )
            finally:
                if page is None:
                    page = await client._checkout_page()
                if video:
                    assert await trash_media(page, project, [video]) == [video]
                if originals is not None:
                    final = await read_project_payload(page, project)
                    assert originals <= {
                        row["media_id"]
                        for row in project_media(final, project)
                        if not row["archived"]
                    }
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 180))
    reset_settings()


@then("all supplied token boundaries are reached without Google generation")
def verified(case):
    assert case["boundaries"] == 3
    assert case["generation_requests"] == 0
