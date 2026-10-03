"""Opt-in free owned synthetic batch deletion/retry; no generation."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports import native_media_delete
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_delete_retries.feature")


@given("an explicitly authorized private synthetic delete retry campaign", target_fixture="case")
def configured(monkeypatch):
    values = {
        k: os.getenv("GFLOW_CLI_E2E_" + k, "") for k in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    output = os.getenv("GFLOW_CLI_E2E_DELETE_RETRIES_OUTPUT", "")
    if not all(values.values()) or not output or os.getenv("GFLOW_CLI_E2E_DELETE_RETRIES") != "1":
        pytest.skip("Explicit free three-upload/delete campaign opt-in required")
    directory = Path(output)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(directory / "allowance-used", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "output": directory, "uploaded": [], "deleted": [], "writes": []}


def checkpoint(case):
    target = case["output"] / "checkpoint.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({k: case[k] for k in ("uploaded", "deleted", "writes")}, stream)


@when("two owned uploads are deleted then retried and mixed with one new owned upload")
def execute(case, monkeypatch):
    fixture = case["output"] / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=purple:s=640x360:d=1",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(fixture),
        ],
        check=True,
        timeout=30,
    )
    original_rpc = native_media_delete.native_rpc

    async def observe(page, rpc, args, source, **kwargs):
        if rpc == "cz8Z4b":
            assert args[6] and set(args[6]) <= set(case["uploaded"])
            assert not set(args[6]) & set(case["deleted"])
            case["writes"].append(list(args[6]))
            checkpoint(case)
        return await original_rpc(page, rpc, args, source, **kwargs)

    monkeypatch.setattr(native_media_delete, "native_rpc", observe)

    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            try:
                before = parse_media_snapshot(await read_project_payload(page, project), project)[
                    "media"
                ]
                originals = {row["media_id"] for row in before}
            finally:
                client._checkin_page(page)
            for _ in range(2):
                result = await client.upload_native_video(
                    project_id=project, path=fixture, rights_confirmed=True
                )
                case["uploaded"].append(result["media_id"])
                checkpoint(case)
            first = await client.delete_native_media(
                project_id=project, media_ids=case["uploaded"].copy(), confirm_delete=True
            )
            assert first["receipt_persisted"] is True
            case["deleted"].extend(first["newly_deleted"])
            checkpoint(case)
            assert len(case["writes"]) == 1
            repeated = await client.delete_native_media(
                project_id=project, media_ids=case["uploaded"].copy(), confirm_delete=True
            )
            assert (
                repeated["already_deleted"] == case["uploaded"] and repeated["newly_deleted"] == []
            )
            assert len(case["writes"]) == 1
            third = await client.upload_native_video(
                project_id=project, path=fixture, rights_confirmed=True
            )
            case["uploaded"].append(third["media_id"])
            checkpoint(case)
            mixed = await client.delete_native_media(
                project_id=project,
                media_ids=[case["uploaded"][0], third["media_id"]],
                confirm_delete=True,
            )
            assert mixed["already_deleted"] == [case["uploaded"][0]]
            assert mixed["newly_deleted"] == [third["media_id"]]
            case["deleted"].extend(mixed["newly_deleted"])
            checkpoint(case)
            assert case["writes"] == [case["uploaded"][:2], [third["media_id"]]]
            page = await client._checkout_page()
            try:
                after = parse_media_snapshot(await read_project_payload(page, project), project)[
                    "media"
                ]
                assert originals <= {row["media_id"] for row in after}
            finally:
                client._checkin_page(page)
            case["originals_preserved"] = True

    asyncio.run(run())


@then("confirmed gone ids cause no replay and original media remains")
def verify(case):
    assert case["deleted"] == case["uploaded"]
    assert case["originals_preserved"] is True
    print(
        "owned_fixture_uploads",
        3,
        "delete_writes",
        2,
        "allgone_retry_writes",
        0,
        "originals_preserved",
        True,
    )
