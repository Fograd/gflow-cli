"""Opt-in free synthetic ingestion/archive; never generates video or deletes originals."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_resources import read_project
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]

scenarios("../features/native_media_adapters.feature")


def checkpoint(case):
    if "output" not in case:
        return
    safe = {
        key: case[key]
        for key in (
            "surface",
            "project",
            "uploaded",
            "archived",
            "archiveAttempted",
            "known",
            "pending",
            "jobId",
            "unknown",
        )
        if key in case
    }
    target = case["output"] / "checkpoint.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(safe, stream)


async def registered_mcp(case, name, arguments):
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + case["token"]}, timeout=240, trust_env=False
    ) as http:
        async with streamable_http_client(case["url"], http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                registered = await session.list_tools()
                assert name in {tool.name for tool in registered.tools}
                result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=240)
                value = result.structured_content
                if value is None:
                    value = json.loads(
                        next(item.text for item in result.content if item.type == "text")
                    )
                remember_unknown(case, value)
                if value.get("status") == "ok" and name == "gflow_upload_video":
                    case["uploaded"] = value["media_id"]
                if value.get("status") == "ok" and name == "gflow_archive_media":
                    if value.get("archived_media_ids") == [case.get("uploaded")]:
                        case["archived"] = True
                checkpoint(case)
                assert result.is_error is not True, "MCP failure: inspect private checkpoint"
                assert value["status"] == "ok", "MCP failed: no automatic replay"
                return value


async def timeline(case: dict[str, Any]) -> list[dict[str, Any]]:
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
    ) as client:
        page = await client._checkout_page()
        try:
            return await read_project(page, case["project"])
        finally:
            client._checkin_page(page)


@pytest.fixture
def media_case() -> Any:
    case: dict[str, Any] = {}
    yield case
    # Cleanup only our acknowledged new fixture, never inferred inventory differences.
    if case.get("uploaded") and not case.get("archived") and not case.get("archiveAttempted"):
        asyncio.run(sdk_archive(case))


@given(parsers.parse('an explicitly authorized "{surface}" media adapter and synthetic owned MP4'))
def owned_fixture(media_case, monkeypatch, tmp_path, surface):
    if os.environ.get("GFLOW_CLI_E2E_NATIVE_MEDIA_SURFACE") != surface:
        pytest.skip("One explicitly coordinated free native-media surface is required")
    if os.environ.get("GFLOW_CLI_E2E_NATIVE_MEDIA_BUDGET") != "1":
        pytest.skip("A one-upload persistent allowance is required")
    directory = os.environ.get("GFLOW_CLI_E2E_NATIVE_MEDIA_OUTPUT", "")
    if not directory:
        pytest.skip("A private persistent allowance/checkpoint directory is required")
    output = Path(directory) / surface
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    media_case.update(surface=surface, output=output, archiveAttempted=False)
    if surface in {"mcp", "http"}:
        variable = "GFLOW_MCP_E2E_URL" if surface == "mcp" else "GFLOW_SELFHOST_E2E_URL"
        media_case["url"] = os.environ.get(variable, "").rstrip("/")
        media_case["token"] = os.environ.get("GFLOW_DAEMON_TOKEN", "")
        if not media_case["url"] or not media_case["token"]:
            pytest.skip("Explicit freshly deployed service URL and bearer required")

    values = {
        key: os.environ.get("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()):
        pytest.skip("Native media lifecycle requires explicit E2E profile/home/project")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    media_case.update(profile=values["PROFILE"], project=values["RESOURCES_PROJECT"])
    path = tmp_path / "owned-synthetic-media.mp4"
    process = subprocess.run(
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
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0 and path.is_file()
    media_case["path"] = path
    descriptor = os.open(output / "allowance", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as allowance:
        allowance.write("one explicitly authorized synthetic upload; never replay\n")
    checkpoint(media_case)
    before = asyncio.run(timeline(media_case))
    media_case["originals"] = {row["media_id"] for row in before if not row["archived"]}
    assert media_case["originals"], "Requires an existing project with original media"


async def sdk_archive(case):
    case["archiveAttempted"] = True
    checkpoint(case)
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
    ) as client:
        result = await client.archive_native_media(
            project_id=case["project"], media_ids=[case["uploaded"]], confirm_archive=True
        )
    assert result["archived_media_ids"] == [case["uploaded"]]
    case["archived"] = True
    checkpoint(case)


def remember_unknown(case, raw):
    from gflow_cli.errors import NativeMediaMutationUnknownError

    if isinstance(raw, NativeMediaMutationUnknownError):
        if raw.project_id != case["project"]:
            return
        if raw.operation == "upload" and len(raw.known_media_ids) == 1:
            case["uploaded"] = raw.known_media_ids[0]
        elif raw.operation == "archive" and case.get("uploaded") in raw.known_media_ids:
            case["archived"] = True
    elif isinstance(raw, dict):
        error = raw.get("error", {})
        if error.get("type") != "https://gflow-cli.dev/errors/native-media-mutation-unknown":
            return
        if error.get("project_id") != case["project"]:
            return
        known = error.get("known_media_ids", [])
        if error.get("operation") == "upload" and len(known) == 1:
            case["uploaded"] = known[0]
        elif error.get("operation") == "archive" and case.get("uploaded") in known:
            case["archived"] = True


def command(case, arguments):
    result = subprocess.run(
        [
            os.sys.executable,
            "-m",
            "gflow_cli.cli",
            "project",
            *arguments,
            "--project",
            case["project"],
            "--profile",
            case["profile"],
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode == 40:
        remember_unknown(case, json.loads(result.stdout))
        case["unknown"] = True
        checkpoint(case)
    assert result.returncode == 0, "Native CLI mutation failed; inspect private proof log"
    return json.loads(result.stdout)


def http_checkpoint(case, value):
    if not isinstance(value, dict):
        return
    if isinstance(value.get("jobId"), str):
        case["jobId"] = value["jobId"]
    response = value.get("response", value)
    details = value.get("errorDetails", {})
    if value.get("outcomeUnknown") is True and isinstance(response, dict):
        if (
            details.get("code") == "submission_outcome_unknown"
            and details.get("operation") == case.get("currentOperation")
            and details.get("phase") in ("dispatch", "response", "cancelled")
            and response.get("projectId") == case["project"]
        ):
            known, pending = (
                response.get("knownMediaGenerationIds", []),
                response.get("pendingMediaGenerationIds", []),
            )
            if (
                isinstance(known, list)
                and isinstance(pending, list)
                and len(known) <= 100
                and len(pending) <= 100
                and all(isinstance(item, str) and len(item) == 36 for item in known + pending)
            ):
                try:
                    known = [str(UUID(item)) for item in known]
                    pending = [str(UUID(item)) for item in pending]
                except ValueError:
                    pass
                else:
                    if not set(known) & set(pending):
                        case.update(known=known, pending=pending, unknown=True)
                        if details["operation"] == "upload" and len(known) == 1:
                            case["uploaded"] = known[0]
                        if details["operation"] == "archive" and case.get("uploaded") in known:
                            case["archived"] = True
    checkpoint(case)


def http_job(client, case, response):
    result = response.json()
    http_checkpoint(case, result)
    assert response.status_code in (200, 201), "HTTP mutation was not accepted; inspect checkpoint"
    deadline = time.monotonic() + 180
    while result.get("status") in ("created", "started"):
        assert time.monotonic() < deadline, "Native HTTP job remains unresolved; do not replay"
        time.sleep(0.5)
        response = client.get(case["http"] + "/jobs/" + result["jobId"])
        result = response.json()
        http_checkpoint(case, result)
        assert response.status_code == 200
    assert result.get("status") in ("ok", "completed"), (
        "Failed HTTP job: inspect private checkpoint"
    )
    return result.get("response", result)


async def operate(case, surface):
    if surface == "sdk":
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            result = await client.upload_native_video(
                project_id=case["project"], path=case["path"], rights_confirmed=True
            )
            case["uploaded"] = result["media_id"]
            checkpoint(case)
        await sdk_archive(case)
    elif surface == "cli":
        result = command(case, ["upload-video", str(case["path"]), "--rights-confirmed"])
        case["uploaded"] = result["media_id"]
        checkpoint(case)
        case["archiveAttempted"] = True
        checkpoint(case)
        result = command(case, ["archive", "--media-id", case["uploaded"], "--confirm-archive"])
        assert result["archived_media_ids"] == [case["uploaded"]]
        case["archived"] = True
        checkpoint(case)
    elif surface == "mcp":
        result = await registered_mcp(
            case,
            "gflow_upload_video",
            {
                "path": str(case["path"]),
                "project": case["project"],
                "rights_confirmed": True,
                "profile": case["profile"],
            },
        )
        case["uploaded"] = result["media_id"]
        checkpoint(case)
        case["archiveAttempted"] = True
        checkpoint(case)
        result = await registered_mcp(
            case,
            "gflow_archive_media",
            {
                "media_ids": [case["uploaded"]],
                "project": case["project"],
                "confirm_archive": True,
                "profile": case["profile"],
            },
        )
        assert result["archived_media_ids"] == [case["uploaded"]]
        case["archived"] = True
        checkpoint(case)
    else:
        case["http"] = case["url"]
        token = case["token"]
        handle = os.environ.get("GFLOW_CLI_E2E_NATIVE_MEDIA_ACCOUNT", "")
        if not handle:
            pytest.skip("HTTP media proof requires explicit mapped account handle")
        with httpx.Client(
            timeout=240, trust_env=False, headers={"Authorization": "Bearer " + token}
        ) as client:
            case["currentOperation"] = "upload"
            response = client.post(
                case["http"] + "/assets/" + handle,
                headers={"Content-Type": "video/mp4", "X-Flow-Rights-Confirmed": "true"},
                content=case["path"].read_bytes(),
            )
            result = http_job(client, case, response)
            case["uploaded"] = result["mediaGenerationId"]["mediaGenerationId"]
            checkpoint(case)
            case["archiveAttempted"] = True
            checkpoint(case)
            case["currentOperation"] = "archive"
            response = client.request(
                "DELETE",
                case["http"] + "/assets/" + handle,
                json={
                    "projectId": case["project"],
                    "mediaGenerationIds": [case["uploaded"]],
                    "async": True,
                },
            )
            result = http_job(client, case, response)
            assert result["deleted"] == [case["uploaded"]]
            case["archived"] = True
            checkpoint(case)


@when(parsers.parse('the "{surface}" adapter uploads and archives only that new fixture'))
def operation(media_case, surface):
    from gflow_cli.errors import NativeMediaMutationUnknownError

    try:
        asyncio.run(operate(media_case, surface))
    except NativeMediaMutationUnknownError as error:
        remember_unknown(media_case, error)
        media_case["unknown"] = True
        checkpoint(media_case)
        raise


@then("the upload is archived and all original active media remain unchanged")
def source_preserved(media_case):
    async def verify():
        deadline = time.monotonic() + 45
        while True:
            after = await timeline(media_case)
            if any(row["media_id"] == media_case["uploaded"] and row["archived"] for row in after):
                break
            assert time.monotonic() < deadline, "Archive acknowledgement awaits timeline visibility"
            await asyncio.sleep(0.5)
        active = {row["media_id"] for row in after if not row["archived"]}
        assert media_case["originals"] <= active
        assert media_case["path"].is_file()

    asyncio.run(verify())
