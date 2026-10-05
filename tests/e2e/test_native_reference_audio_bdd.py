"""R04 current native audio proof; one optional free source upload, zero generation."""

import asyncio
import inspect
import os
import shutil
import subprocess

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api import native_video_edit as edit
from gflow_cli.api import recaptcha
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_extension import _read_native, parse_extension_models
from gflow_cli.api.native_reference_video import reference_args
from gflow_cli.api.native_video_characters import model_reference_limits, reference_capacity
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.migrated_video_upload import upload_video
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_reference_audio.feature")


class PreflightCompleteError(Exception):
    """Raised before the real token minter, output checkpoint or dispatch."""


@given(
    "an explicit profile project and existing audio for video reference preflight",
    target_fixture="case",
)
def configured(monkeypatch, tmp_path):
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT", "REFERENCE_AUDIO")
    }
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_REFERENCE_AUDIO_PREFLIGHT") != "1":
        pytest.skip("Explicit private audio preflight inputs required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "tmp": tmp_path, "boundaries": 0, "generation_requests": 0}


@when("fresh audio and model data build reference and edit requests at the mint boundary")
def preflight(case, monkeypatch):
    audio = case["REFERENCE_AUDIO"]

    class Gate:
        async def mint(self, action):
            assert action == "VIDEO_GENERATION"
            # Inspect the actual adapter's already-resolved fresh inputs. The real
            # minter is never called; the final codecs get a local inert sentinel.
            frame = inspect.currentframe().f_back
            try:
                values = frame.f_locals
                is_edit = frame.f_code.co_name == "edit_native_video"
                if is_edit:
                    args = edit.video_edit_args(
                        values["started"],
                        prompt=values["prompt"],
                        model_key=values["model_key"],
                        aspect=values["aspect"],
                        token="preflight-only",
                        start_frame=values["start_frame"],
                        end_frame=values["end_frame"],
                        image_ids=values["image_ids"],
                        audio_ids=values["audio_ids"],
                        character_ids=values["character_ids"],
                        reference_slots=values["slots"],
                    )
                else:
                    args = reference_args(
                        values["started"],
                        prompt=values["prompt"],
                        model_key=values["key"],
                        aspect=values["aspect"],
                        resolution=values["resolution"],
                        token="preflight-only",
                        image_ids=values["images"],
                        audio_ids=values["audio"],
                        character_ids=values["characters"],
                        reference_slots=values["slots"],
                    )
                row = args[0][0]
                assert row[9 if is_edit else 7] == [[audio]]
                assert row[1 if is_edit else 0][2][0] == [
                    ["Use "],
                    [None, [None, [audio, ""]]],
                    [" twice "],
                    [None, [None, [audio, ""]]],
                ]
                case["boundaries"] += 1
            finally:
                del frame
            raise PreflightCompleteError

    monkeypatch.setattr(edit, "TokenMinter", lambda *_, **__: Gate())
    monkeypatch.setattr(recaptcha, "TokenMinter", lambda *_, **__: Gate())

    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            video = None
            fixture = None
            originals = None

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

            await client._context.route("**/batchexecute*", guard)
            try:
                payload = await read_project_payload(page, project)
                edit.validate_edit_audio(payload, project, (audio,))
                originals = {
                    row["media_id"]
                    for row in project_media(payload, project)
                    if not row["archived"]
                }
                video = os.getenv("GFLOW_CLI_E2E_REFERENCE_AUDIO_VIDEO")
                if not video:
                    if os.getenv("GFLOW_CLI_E2E_REFERENCE_AUDIO_SOURCE_FIXTURE") != "1":
                        pytest.skip(
                            "Existing source or explicit free source-fixture opt-in required"
                        )
                    if not shutil.which("ffmpeg"):
                        pytest.skip("Source fixture requires ffmpeg")
                    path = case["tmp"] / "R04-audio-preflight-source.mp4"
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
                    video, _ = await upload_video(page, project, path, rights_confirmed=True)
                    fixture = video
                models = await _read_native(page, "HTrJv", [], project)
                tier = await _read_native(page, "nzlxg", [], project)
                eligible = [
                    row
                    for row in parse_extension_models(
                        models, tier=tier[3], required_requirements=(1, 6, 20)
                    )
                    if reference_capacity(
                        0, 1, {}, model_reference_limits(models, row["model_key"])
                    )
                ]
                assert eligible, "No current edit model supports one audio ingredient"
                key = min(eligible, key=lambda row: row["credits"])["model_key"]
                client._checkin_page(page)
                page = None
                kwargs = {
                    "project_id": project,
                    "prompt": "Use @referenceAudio_3 twice @referenceAudio_3",
                    "reference_slot_ids": {"referenceAudio_3": audio},
                }
                with pytest.raises(PreflightCompleteError):
                    await client.generate_native_reference_video(
                        reference_audio_ids=(audio,), **kwargs
                    )
                with pytest.raises(PreflightCompleteError):
                    await client.edit_native_video(
                        media_id=video, model_key=key, end_frame=24, audio_ids=(audio,), **kwargs
                    )
            finally:
                if page is None:
                    page = await client._checkout_page()
                if fixture:
                    assert await trash_media(page, project, [fixture]) == [fixture]
                if originals is not None:
                    final = await read_project_payload(page, project)
                    active = {
                        row["media_id"]
                        for row in project_media(final, project)
                        if not row["archived"]
                    }
                    assert originals <= active
                    if fixture:
                        assert fixture not in active
                client._checkin_page(page)

    try:
        asyncio.run(asyncio.wait_for(run(), 180))
    finally:
        reset_settings()


@then("both requests retain audio slot three and no token or generation is sent")
def verified(case):
    assert case["boundaries"] == 2
    assert case["generation_requests"] == 0
