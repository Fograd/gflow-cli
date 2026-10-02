"""Opt-in native CLI/MCP lifecycle proof; uses existing images, never generates.

Requires GFLOW_CLI_E2E_PROFILE, GFLOW_NATIVE_CHARACTER_E2E_PROJECT,
GFLOW_NATIVE_CHARACTER_E2E_IMAGE_1 and GFLOW_NATIVE_CHARACTER_E2E_IMAGE_2.
GFLOW_NATIVE_CHARACTER_E2E_HOME optionally selects a private deployment home.
Only uniquely named entities created by this test are removed. No retry after
unknown mutation outcomes; a returned partial identity is retained for cleanup.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.mcp import tools

scenarios("../features/native_character_surface_lifecycle.feature")


def _cli(case: dict[str, Any], command: str, *args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gflow_cli.cli",
            "character",
            command,
            "--project",
            case["project"],
            "--profile",
            case["profile"],
            "--json",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=150,
        check=False,
    )
    result = json.loads(completed.stdout)
    # Preserve an acknowledged partial identity without replaying the mutation.
    problem = result.get("error", result)
    partial = problem.get("character_ref")
    if partial:
        case["created"] = partial
    assert completed.returncode == 0, "native CLI operation failed; inspect private test output"
    assert result.get("status") == "ok"
    return result


def _mcp(case: dict[str, Any], command: str, **kwargs: Any) -> dict[str, Any]:
    function = getattr(tools, "gflow_character_" + command)
    result = asyncio.run(function(project=case["project"], profile=case["profile"], **kwargs))
    partial = result.get("error", {}).get("character_ref")
    if partial:
        case["created"] = partial
    assert result.get("status") == "ok", "native MCP operation failed; inspect private test output"
    return result


@pytest.fixture
def native_case(monkeypatch: pytest.MonkeyPatch):
    names = {
        "profile": "GFLOW_CLI_E2E_PROFILE",
        "project": "GFLOW_NATIVE_CHARACTER_E2E_PROJECT",
        "image1": "GFLOW_NATIVE_CHARACTER_E2E_IMAGE_1",
        "image2": "GFLOW_NATIVE_CHARACTER_E2E_IMAGE_2",
    }
    case: dict[str, Any] = {key: os.environ.get(env, "").strip() for key, env in names.items()}
    if not all(case.values()):
        pytest.skip("set the private native-character lifecycle environment variables")
    home = os.environ.get("GFLOW_NATIVE_CHARACTER_E2E_HOME", "").strip()
    if home:
        monkeypatch.setenv("GFLOW_CLI_HOME", home)
    else:
        monkeypatch.delenv("GFLOW_CLI_HOME", raising=False)
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    case.update(name="adapter-proof-" + uuid.uuid4().hex[:12], created=None)
    try:
        yield case
    finally:
        if case["created"]:
            # Cleanup only the identity acknowledged for this test's own creation.
            _mcp(case, "rm", entity_id=case["created"], confirm_delete=True)
        reset_settings()


@given("two owned native images and a logged in character profile")
def configured(native_case):
    assert native_case["image1"] != native_case["image2"]


@when(
    parsers.parse(
        "the {surface} adapter creates a character with two references and a preset voice"
    )
)
def create(native_case, surface):
    if surface == "CLI":
        result = _cli(
            native_case,
            "create-from-images",
            "--name",
            native_case["name"],
            "--image-reference-1",
            native_case["image1"],
            "--image-reference-2",
            native_case["image2"],
            "--personality",
            "Initial adapter proof notes",
            "--voice",
            "Charon",
        )
    else:
        result = _mcp(
            native_case,
            "create_from_images",
            display_name=native_case["name"],
            image_reference_1=native_case["image1"],
            image_reference_2=native_case["image2"],
            personality="Initial adapter proof notes",
            voice="Charon",
        )
    character = result["character"]
    native_case["created"] = character["entity_id"]
    assert len(character["workflow_ids"]) == 2
    assert character["personality"] == "Initial adapter proof notes"
    assert character["voice"].casefold() == "charon"


@then(parsers.parse("the {surface} adapter can update, read and delete only that character"))
def lifecycle(native_case, surface):
    entity = native_case["created"]
    if surface == "CLI":
        listed = _cli(native_case, "list")
        _cli(native_case, "update", "--id", entity, "--personality", "")
        cleared = _cli(native_case, "show", "--id", entity)
    else:
        listed = _mcp(native_case, "list")
        _mcp(native_case, "update", entity_id=entity, personality="")
        cleared = _mcp(native_case, "show", entity_id=entity)
    assert any(item["entity_id"] == entity for item in listed["characters"])
    assert cleared["character"]["personality"] in (None, "")
    new_name = native_case["name"] + "-updated"
    if surface == "CLI":
        _cli(
            native_case,
            "update",
            "--id",
            entity,
            "--name",
            new_name,
            "--personality",
            "Updated adapter proof notes",
            "--voice",
            "Aoede",
        )
        result = _cli(native_case, "show", "--id", entity)
    else:
        _mcp(
            native_case,
            "update",
            entity_id=entity,
            display_name=new_name,
            personality="Updated adapter proof notes",
            voice="Aoede",
        )
        result = _mcp(native_case, "show", entity_id=entity)
    character = result["character"]
    assert character["entity_id"] == entity
    assert character["display_name"] == new_name
    assert character["personality"] == "Updated adapter proof notes"
    assert character["voice"].casefold() == "aoede"
    assert len(character["workflow_ids"]) == 2
    assert "https://" not in json.dumps(character)
    if surface == "CLI":
        _cli(native_case, "rm", "--id", entity, "--yes")
    else:
        _mcp(native_case, "rm", entity_id=entity, confirm_delete=True)
    native_case["created"] = None
