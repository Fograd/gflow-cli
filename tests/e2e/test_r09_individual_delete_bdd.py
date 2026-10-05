"""Opt-in two-fixture R09 campaign. Never infer ownership or replay a mutation."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import project_catalog_snapshot
from gflow_cli.api.transports import native_media_delete
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.api.transports.migrated_rpc import NativeMetadataRpcError, native_rpc
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/r09_individual_delete.feature")


def checkpoint(case):
    fd, name = tempfile.mkstemp(dir=case["output"])
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({key: value for key, value in case.items() if key != "output"}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, case["output"] / "manifest.json")
    finally:
        Path(name).unlink(missing_ok=True)


async def snapshot(client, project):
    page = await client._checkout_page()
    try:
        catalog = project_catalog_snapshot(await read_project_payload(page, project), project)
        return {
            key: sorted({row[field] for row in catalog[key]})
            for key, field in (
                ("media", "media_id"),
                ("workflows", "workflow_id"),
                ("characters", "entity_id"),
                ("user_voices", "ref"),
            )
        }
    finally:
        client._checkin_page(page)


async def exact_gone(client, project, identifier):
    page = await client._checkout_page()
    try:
        await page.goto("https://flow.google.com/project/" + project, wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=15000)
        for attempt in range(11):
            try:
                await native_rpc(
                    page, "as29s", [identifier], "/project/" + project, require_single=True
                )
            except NativeMetadataRpcError as error:
                assert error.rpcid == "as29s" and type(error.code) is int and error.code == 5
                return
            if attempt < 10:
                await asyncio.sleep(2)
        pytest.fail("Exact NOT_FOUND not visible within bounded read-only polling; no replay")
    finally:
        client._checkin_page(page)


@given("an explicitly authorised R09 image and video fixture allowance", target_fixture="case")
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE")
    project = os.getenv("GFLOW_CLI_E2E_RESOURCES_PROJECT")
    output = os.getenv("GFLOW_CLI_E2E_R09_OUTPUT")
    if (
        os.getenv("GFLOW_CLI_E2E_R09") != "1"
        or profile not in {"pro2", "pro3"}
        or not project
        or not output
    ):
        pytest.skip("Requires explicit R09 two-fixture allowance and original pro2/pro3 scope")
    directory = Path(output)
    home = os.getenv("GFLOW_CLI_E2E_HOME")
    if not home:
        pytest.skip("Requires the explicitly selected original profile home")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / "allowance-used", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    return {
        "profile": profile,
        "project": project,
        "output": directory,
        "fixtures": [],
        "writes": [],
    }


@when("SDK first deletion and CLI mixed deletion use only acknowledged fixture IDs")
def execute(case, monkeypatch):
    project = case["project"]
    image_path = case["output"] / "R09_INVOCATION_SYNTHETIC_IMAGE.png"
    video_path = case["output"] / "R09_INVOCATION_SYNTHETIC_VIDEO.mp4"
    Image.new("RGB", (640, 360), "orange").save(image_path)
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
            str(video_path),
        ],
        check=True,
        timeout=30,
    )
    original_rpc = native_media_delete.native_rpc

    async def observe(page, rpcid, payload, source, **kwargs):
        if rpcid == "cz8Z4b":
            allowed = {row["id"] for row in case["fixtures"]}
            assert set(payload[6]) <= allowed and payload[2] == project and payload[1] is None
            case["writes"].append(payload[6])
            checkpoint(case)
        return await original_rpc(page, rpcid, payload, source, **kwargs)

    monkeypatch.setattr(native_media_delete, "native_rpc", observe)

    async def first():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            case["originals"] = await snapshot(client, project)
            checkpoint(case)
            for kind, path in (("image", image_path), ("video", video_path)):
                case["phase"] = "upload-" + kind
                checkpoint(case)
                if kind == "image":
                    result = await client.upload_reference(project, path)
                    identifier = result.name
                else:
                    result = await client.upload_native_video(
                        project_id=project, path=path, rights_confirmed=True
                    )
                    identifier = result["media_id"]
                assert identifier not in case["originals"]["media"]
                case["fixtures"].append({"id": identifier, "kind": kind, "acknowledged": True})
                checkpoint(case)
            image, video = [row["id"] for row in case["fixtures"]]
            case["phase"] = "sdk-first-delete"
            checkpoint(case)
            result = await client.delete_native_media(
                project_id=project, media_ids=[image.upper(), image], confirm_delete=True
            )
            assert result["newly_deleted"] == [image] and result["receipt_persisted"] is True
            await exact_gone(client, project, image)
            sibling = await client.get_native_asset(project, video)
            assert sibling.media_id == video
            case["unrequested_sibling_preserved"] = True
            case["sdk_first"] = result
            checkpoint(case)

    asyncio.run(first())
    image, video = [row["id"] for row in case["fixtures"]]
    case["phase"] = "cli-mixed-delete"
    checkpoint(case)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gflow_cli",
            "project",
            "delete-media",
            "--project",
            project,
            "--profile",
            case["profile"],
            "--media-id",
            image,
            "--media-id",
            video.upper(),
            "--media-id",
            video,
            "--confirm-delete",
            "--json",
        ],
        capture_output=True,
        timeout=180,
        check=False,
    )
    (case["output"] / "cli-private-output.json").write_bytes(completed.stdout)
    (case["output"] / "cli-private-output.json").chmod(0o600)
    assert completed.returncode == 0, "CLI failed; inspect private checkpoint, never replay"
    result = json.loads(completed.stdout)
    assert result["already_deleted"] == [image] and result["newly_deleted"] == [video]
    assert result["receipt_persisted"] is True
    case["cli_mixed"] = result
    checkpoint(case)

    async def verify():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            await exact_gone(client, project, video)
            case["phase"] = "sdk-repeat"
            checkpoint(case)
            repeated = await client.delete_native_media(
                project_id=project, media_ids=[image, video], confirm_delete=True
            )
            assert repeated["already_deleted"] == [image, video] and repeated["newly_deleted"] == []
            assert case["writes"] == [[image]]
            after = await snapshot(client, project)
            for key, identities in case["originals"].items():
                assert set(identities) <= set(after[key]), "Original identities changed"
            case.update(
                phase="complete", exact_gone=True, originals_preserved=True, fixture_cleanup=True
            )
            checkpoint(case)

    asyncio.run(verify())


@then("exact gone evidence and receipts allow zero-write repeats and originals survive")
def verified(case):
    assert case["phase"] == "complete" and case["fixture_cleanup"]
    print(
        "R09 SDK first/image, CLI mixed/video, SDK zero-write repeat passed; "
        "originals preserved; fixtures2 cleaned"
    )
