"""Free video/character fixture validates SDK edit preflight before token mint."""

import asyncio
import os
import shutil
import subprocess
import uuid

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api import native_video_edit as edit
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_extension import _read_native, parse_extension_models
from gflow_cli.api.native_video_characters import (
    character_reference_counts,
    model_reference_limits,
    reference_capacity,
)
from gflow_cli.api.transports.migrated_characters import mutate_character
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.migrated_video_upload import upload_video
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_edit_characters.feature")


class PreflightCompleteError(Exception):
    pass


@given(
    "an explicit profile and free synthetic video for character edit preflight",
    target_fixture="case",
)
def configured(monkeypatch, tmp_path):
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if (
        not all(values.values())
        or os.getenv("GFLOW_CLI_E2E_EDIT_CHARACTERS") != "1"
        or not shutil.which("ffmpeg")
    ):
        pytest.skip("Explicit private free-fixture opt-in and ffmpeg required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    path = tmp_path / "edit-character-source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=yellow:s=256x144:r=24:d=1",
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
    return {
        **values,
        "path": path,
        "generation_requests": 0,
        "token_boundary": False,
        "cleaned": False,
    }


@when("the native SDK validates source character and model capacities before minting")
def preflight(case, monkeypatch):
    class Gate:
        async def mint(self, action):
            assert action == "VIDEO_GENERATION"
            case["token_boundary"] = True
            raise PreflightCompleteError

    monkeypatch.setattr(edit, "TokenMinter", lambda *_, **__: Gate())

    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            character = None
            video = None
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
                        "maseQ",
                    )
                ):
                    case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            try:
                initial = await read_project_payload(page, project)
                originals = {
                    row["media_id"]
                    for row in project_media(initial, project)
                    if not row["archived"]
                }
                image = next(
                    row
                    for row in parse_media_snapshot(initial, project)["media"]
                    if row["kind"] == "image"
                )
                created = await mutate_character(
                    page,
                    project,
                    "create",
                    name="edit-character-bdd-" + uuid.uuid4().hex[:12],
                    source_media_id=image["media_id"],
                    image_reference_confirmed=True,
                )
                character = created["character"]["entity_id"]
                video, _ = await upload_video(page, project, case["path"], rights_confirmed=True)
                for _ in range(10):
                    payload = await read_project_payload(page, project)
                    if any(row["media_id"] == video for row in project_media(payload, project)):
                        break
                    await asyncio.sleep(0.5)
                weights = character_reference_counts(payload, project, (character,))
                models = await _read_native(page, "HTrJv", [], project)
                credits = await _read_native(page, "nzlxg", [], project)
                options = parse_extension_models(
                    models, tier=credits[3], required_requirements=(1, 6, 20)
                )
                eligible = [
                    row
                    for row in options
                    if reference_capacity(
                        0, 0, weights, model_reference_limits(models, row["model_key"])
                    )
                ]
                assert eligible, "No observed native edit model supports the fixture character"
                key = min(eligible, key=lambda row: row["credits"])["model_key"]
                client._checkin_page(page)
                page = None
                with pytest.raises(PreflightCompleteError):
                    await client.edit_native_video(
                        project_id=project,
                        media_id=video,
                        prompt="Use @referenceImage_3",
                        model_key=key,
                        character_ids=(),
                        image_ids=(character,),
                        reference_slot_ids={"referenceImage_3": character},
                        end_frame=24,
                    )
            finally:
                if page is None:
                    page = await client._checkout_page()
                try:
                    if character:
                        await mutate_character(page, project, "delete", entity_id=character)
                    if video:
                        assert await trash_media(page, project, [video]) == [video]
                    final = await read_project_payload(page, project)
                    active = {
                        row["media_id"]
                        for row in project_media(final, project)
                        if not row["archived"]
                    }
                    if originals is not None:
                        assert originals <= active
                    case["cleaned"] = True
                finally:
                    await page.unroute("**/batchexecute*", guard)
                    client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 240))
    reset_settings()


@then("preflight reaches the token boundary without generation and only the fixtures are removed")
def verified(case):
    assert case["token_boundary"] and case["cleaned"]
    assert case["generation_requests"] == 0
