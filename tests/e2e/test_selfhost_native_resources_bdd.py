"""Opt-in zero-credit resource BDD: PROFILE, HOME, RESOURCES_PROJECT E2E env inputs."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_resources import read_project, trash_media
from gflow_cli.api.transports.migrated_video_upload import upload_video
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/selfhost_native_resources.feature")


@given(
    "an authenticated profile and a self-created one-second video", target_fixture="resource_case"
)
def resource_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    values = {
        key: os.environ.get(f"GFLOW_CLI_E2E_{key}", "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()) or not shutil.which("ffmpeg"):
        pytest.skip("Native resource BDD requires documented E2E inputs and ffmpeg")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    path = tmp_path / "native-resource-bdd.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=yellow:s=256x256:r=24:d=1",
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
    return {**values, "path": path}


async def _exercise(case: dict[str, Any]) -> dict[str, Any]:
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
        try:
            project = case["RESOURCES_PROJECT"]
            media_id, _ = await upload_video(page, project, case["path"], rights_confirmed=True)
            rows = await read_project(page, project)
            for _ in range(10):
                if any(row["media_id"] == media_id for row in rows):
                    break
                await asyncio.sleep(0.5)
                rows = await read_project(page, project)
            assert any(row["media_id"] == media_id for row in rows)
            deleted = await trash_media(page, project, [media_id])
            after = await read_project(page, project)
            for _ in range(10):
                if any(row["media_id"] == media_id and row["archived"] for row in after):
                    break
                await asyncio.sleep(0.5)
                after = await read_project(page, project)
            assert any(row["media_id"] == media_id and row["archived"] for row in after)
            return {"media_id": media_id, "deleted": deleted, "listed": True, "archived": True}
        finally:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


@when("the native driver uploads and archives the video with explicit rights confirmation")
def resource_operations(resource_case: dict[str, Any]) -> None:
    resource_case["result"] = asyncio.run(_exercise(resource_case))


@then("the returned media identity is present in the native project and archive acknowledgement")
def verify_resource_identity(resource_case: dict[str, Any]) -> None:
    result = resource_case["result"]
    assert result["deleted"] == [result["media_id"]]
    assert result["listed"] and result["archived"]
