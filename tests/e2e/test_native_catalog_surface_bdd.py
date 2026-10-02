"""Read-only CLI/MCP native inventory proof, no generation or solver calls.

Requires GFLOW_CLI_E2E_PROFILE, GFLOW_NATIVE_CHARACTER_E2E_PROJECT and
GFLOW_NATIVE_CHARACTER_E2E_HOME (same private fixture as the character proof).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.mcp import tools

scenarios("../features/native_catalog_surface_inventory.feature")


@given("a logged in native inventory profile and project", target_fixture="inventory_case")
def inventory_case(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    names = {
        "profile": "GFLOW_CLI_E2E_PROFILE",
        "project": "GFLOW_NATIVE_CHARACTER_E2E_PROJECT",
        "home": "GFLOW_NATIVE_CHARACTER_E2E_HOME",
    }
    case: dict[str, Any] = {key: os.environ.get(env, "").strip() for key, env in names.items()}
    if not all(case.values()):
        pytest.skip("set the private native inventory proof inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", case["home"])
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return case


def _cli(case: dict[str, Any], command: str, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gflow_cli.cli",
            "project",
            command,
            "--source",
            "google",
            "--profile",
            case["profile"],
            "--json",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, "native CLI inventory failed; inspect private evidence"
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    return data


@when("CLI and MCP read native project pages and project media")
def read_inventory(inventory_case: dict[str, Any]) -> None:
    case = inventory_case
    case["cli_projects"] = _cli(case, "list")
    case["mcp_projects"] = asyncio.run(
        tools.gflow_list_projects(source="google", profile=case["profile"])
    )
    cursor = case["cli_projects"]["next_cursor"]
    assert cursor, "fixture account must have a second project page"
    case["cli_second"] = _cli(case, "list", "--cursor", cursor)
    case["mcp_second"] = asyncio.run(
        tools.gflow_list_projects(source="google", cursor=cursor, profile=case["profile"])
    )
    case["cli_media"] = _cli(case, "media", "--project", case["project"])
    case["mcp_media"] = asyncio.run(
        tools.gflow_project_media(project=case["project"], profile=case["profile"])
    )


@then("their IDs and mixed media kinds agree with unknown completeness")
def check_inventory(inventory_case: dict[str, Any]) -> None:
    case = inventory_case
    for key in [
        "cli_projects",
        "mcp_projects",
        "cli_second",
        "mcp_second",
        "cli_media",
        "mcp_media",
    ]:
        assert case[key]["status"] == "ok"
        assert case[key]["complete"] is None

    def ids(key: str) -> set[str]:
        return {row["project_id"] for row in case[key]["projects"]}

    assert ids("cli_projects") == ids("mcp_projects")
    assert ids("cli_second") == ids("mcp_second")
    assert ids("cli_projects").isdisjoint(ids("cli_second"))

    def media(key: str) -> dict[str, str]:
        return {row["media_id"]: row["kind"] for row in case[key]["media"]}

    assert media("cli_media") == media("mcp_media")
    assert {"image", "video"} <= set(media("cli_media").values())
    assert "https://" not in json.dumps(case["cli_media"])
