"""One opt-in public invocation per adapter; never replay an uncertain request.

CLI is a real subprocess, MCP uses its registered HTTP protocol, and HTTP uses
an operator-selected deployed endpoint. All identifiers and outputs stay in a
private output directory. A persistent allowance marker prevents rerunning a
surface even when the first invocation times out. This proves one invocation
and one returned output, not an independent count of native wire dispatches.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest, ImageRef
from gflow_cli.api.native_image_references import validate_native_image_references
from gflow_cli.api.reference_markers import prepare_ordered_image_slots
from gflow_cli.api.transports.migrated_characters import CharacterBindingError, mutate_character
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_adapter_grounding.feature")
PROMPT = "Draw @reference_1 beside @character_1 and @reference_1."


def _private_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)


def _queue_idle(case: dict[str, Any]) -> None:
    with sqlite3.connect(Path(case["GROUNDING_QUEUE_DB"]).as_uri() + "?mode=ro", uri=True) as db:
        pending = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE state IN ('created','running')"
        ).fetchone()[0]
    assert pending == 0, "Production queue must be idle before profile operations"


async def _fixture_operation(case: dict[str, Any], create: bool) -> None:
    _queue_idle(case)
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
        try:
            if create:
                try:
                    result = await mutate_character(
                        page,
                        case["RESOURCES_PROJECT"],
                        "create",
                        name=case["name"],
                        source_media_id=case["CHARACTER_FIRST_MEDIA"],
                        image_reference_confirmed=True,
                    )
                    case["entity"] = result["character"]["entity_id"]
                except CharacterBindingError as error:
                    case["entity"] = error.entity_id
                    raise
            else:
                await mutate_character(page, case["RESOURCES_PROJECT"], "delete", case["entity"])
            payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
            active = {
                row["media_id"]
                for row in project_media(payload, case["RESOURCES_PROJECT"])
                if not row["archived"]
            }
            assert {case["CHARACTER_FIRST_MEDIA"], case["GROUNDING_MEDIA"]} <= active
            if not create:
                case["entity"] = ""
                case["cleaned"] = True
        finally:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def _metadata_preflight(case: dict[str, Any]) -> None:
    """Prove fixture/reference eligibility without minting or submitting."""
    _queue_idle(case)
    request = prepare_ordered_image_slots(
        GenerateImageRequest(
            prompt=PROMPT,
            reference_syntax="slots",
            count=1,
            refs=(ImageRef(case["GROUNDING_MEDIA"]),),
            reference_entities=(case["entity"],),
        )
    )
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        result = await validate_native_image_references(client, case["RESOURCES_PROJECT"], request)
        assert result.refs[0].in_project and result.refs[0].display_name
        case["metadata_preflight_passed"] = True


@pytest.fixture
def adapter_case(monkeypatch: pytest.MonkeyPatch):
    keys = (
        "PROFILE",
        "HOME",
        "RESOURCES_PROJECT",
        "CHARACTER_FIRST_MEDIA",
        "GROUNDING_MEDIA",
        "GROUNDING_OUTPUT",
        "GROUNDING_QUEUE_DB",
    )
    case: dict[str, Any] = {key: os.environ.get("GFLOW_CLI_E2E_" + key, "") for key in keys}
    case.update(
        entity="", cleaned=False, invocations=0, name="adapter-grounding-" + uuid4().hex[:10]
    )
    if not all(case[key] for key in keys):
        pytest.skip("Private authenticated profile and owned references required")
    monkeypatch.setenv("GFLOW_CLI_HOME", case["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_FLOW_HOST", "flow.google.com")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    try:
        yield case
    finally:
        if case["entity"]:
            asyncio.run(_fixture_operation(case, False))
        reset_settings()


@given(
    parsers.parse("an explicitly authorized {surface} grounding adapter and owned source images")
)
def authorized(adapter_case: dict[str, Any], surface: str) -> None:
    if os.environ.get("GFLOW_CLI_E2E_GROUNDING_SURFACE") != surface:
        pytest.skip("One explicitly coordinated surface lease is required")
    if os.environ.get("GFLOW_CLI_E2E_GROUNDING_BUDGET") != "1":
        pytest.skip("One-image adapter allowance required")
    case = adapter_case
    case["surface"] = surface
    case["output"] = Path(case["GROUNDING_OUTPUT"]) / surface.lower()
    case["output"].mkdir(mode=0o700, parents=True, exist_ok=True)
    case["output"].chmod(0o700)
    if surface in {"MCP", "HTTP"}:
        variable = "GFLOW_MCP_E2E_URL" if surface == "MCP" else "GFLOW_SELFHOST_E2E_URL"
        case["url"] = os.environ.get(variable, "").rstrip("/")
        case["token"] = os.environ.get("GFLOW_DAEMON_TOKEN", "")
        if not case["url"] or not case["token"]:
            pytest.skip("Coordinated deployed adapter URL and bearer required")
    asyncio.run(_fixture_operation(case, True))
    asyncio.run(_metadata_preflight(case))


async def _registered_mcp(case: dict[str, Any]) -> dict[str, Any]:
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + case["token"]}, timeout=360, trust_env=False
    ) as http:
        async with streamable_http_client(case["url"], http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert "gflow_generate_image" in {tool.name for tool in listed.tools}
                result = await asyncio.wait_for(
                    session.call_tool(
                        "gflow_generate_image",
                        {
                            "prompt": PROMPT,
                            "model": "nano2",
                            "aspect": "1:1",
                            "count": 1,
                            "reference_syntax": "slots",
                            "reference_images": [case["GROUNDING_MEDIA"]],
                            "reference_entities": [case["entity"]],
                            "profile": case["PROFILE"],
                            "project": case["RESOURCES_PROJECT"],
                            "output": str(case["output"] / "image.jpg"),
                            "wait": True,
                        },
                    ),
                    timeout=360,
                )
                value = result.structured_content
                if value is None:
                    value = json.loads(
                        next(item.text for item in result.content if item.type == "text")
                    )
                _private_json(case["output"] / "checkpoint.json", value)
                assert result.is_error is not True, "MCP failed; inspect private checkpoint"
                return value


def _http(case: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(
        headers={"Authorization": "Bearer " + case["token"]}, timeout=120, trust_env=False
    ) as client:
        response = client.post(
            case["url"] + "/images",
            json={
                "prompt": PROMPT,
                "model": "nano-banana-2",
                "count": 1,
                "aspectRatio": "1:1",
                "reference_1": case["GROUNDING_MEDIA"],
                "character_1": case["entity"],
                "projectId": case["RESOURCES_PROJECT"],
                "async": True,
            },
        )
        _private_json(case["output"] / "checkpoint.json", response.json())
        assert response.status_code == 201, "HTTP refused; inspect private checkpoint"
        job = response.json()
        deadline = time.monotonic() + 360
        while job["status"] in {"created", "started"} and time.monotonic() < deadline:
            time.sleep(1)
            response = client.get(case["url"] + "/jobs/" + job["jobId"])
            response.raise_for_status()
            job = response.json()
        _private_json(case["output"] / "checkpoint.json", job)
        assert job["status"] == "completed", "Uncertain/failed job must not be replayed"
        media = job["response"]["media"]
        assert len(media) == 1
        data = base64.b64decode(media[0]["image"]["generatedImage"]["encodedImage"], validate=True)
        path = case["output"] / "image.jpg"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        return {"status": "completed", "files": [str(path)]}


@when("that adapter receives one canonical count-one image request")
def request_once(adapter_case: dict[str, Any]) -> None:
    case = adapter_case
    _queue_idle(case)
    assert case["metadata_preflight_passed"]
    # Consume permission before public invocation; a timeout cannot grant a retry.
    descriptor = os.open(
        case["output"] / "allowance-used", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    os.close(descriptor)
    case["invocations"] += 1
    if case["surface"] == "CLI":
        result = subprocess.run(
            [
                os.environ.get("GFLOW_CLI_E2E_CLI_PYTHON", sys.executable),
                "-m",
                "gflow_cli.cli",
                "image",
                "i2i",
                PROMPT,
                "--ref",
                case["GROUNDING_MEDIA"],
                "--reference-entity",
                case["entity"],
                "--reference-syntax",
                "slots",
                "--project",
                case["RESOURCES_PROJECT"],
                "--profile",
                case["PROFILE"],
                "--model",
                "nano2",
                "--aspect",
                "1:1",
                "--count",
                "1",
                "--output",
                str(case["output"] / "image.jpg"),
                "--json",
            ],
            cwd=os.environ.get("GFLOW_CLI_E2E_CLI_CWD"),
            env={
                **os.environ,
                "PYTHONPATH": os.environ.get(
                    "GFLOW_CLI_E2E_CLI_PYTHONPATH", os.environ.get("PYTHONPATH", "")
                ),
            },
            capture_output=True,
            text=True,
            timeout=360,
            check=False,
        )
        value = json.loads(result.stdout)
        _private_json(case["output"] / "checkpoint.json", value)
        assert result.returncode == 0, "CLI failed; inspect private checkpoint"
        assert value["status"] == "ok" and len(value["images"]) == 1
        paths = [value["images"][0]["local_path"]]
    elif case["surface"] == "MCP":
        value = asyncio.run(_registered_mcp(case))
        assert value["status"] == "completed", "MCP failure must not be replayed"
        paths = value["files"]
    else:
        paths = _http(case)["files"]
    assert len(paths) == 1
    with Image.open(paths[0]) as image:
        image.load()
        assert image.width >= 1024 and image.height >= 1024
    case["decoded"] = True
    asyncio.run(_fixture_operation(case, False))


@then("one output decodes and only the owned character fixture is removed")
def verify(adapter_case: dict[str, Any]) -> None:
    assert adapter_case["invocations"] == 1
    assert adapter_case["decoded"] and adapter_case["cleaned"]
