from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_project
from gflow_cli.cli import main
from gflow_cli.mcp import tools

PROJECT = "11111111-1111-4111-8111-111111111111"
PROJECTS = {
    "projects": [],
    "next_cursor": "opaque",
    "returned_count": 0,
    "scope": "native Google account projects",
    "complete": None,
}
MEDIA = {
    "media": [],
    "project_id": PROJECT,
    "returned_count": 0,
    "scope": "native selected project timeline",
    "complete": None,
}


def _client(monkeypatch, module):
    client = MagicMock()
    client.list_native_projects = AsyncMock(return_value=PROJECTS)
    client.list_native_media = AsyncMock(return_value=MEDIA)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(module, "FlowApiClient", lambda **kw: context)
    return client


def test_cli_native_projects_forwards_opaque_cursor(monkeypatch):
    client = _client(monkeypatch, cli_project)
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(
        main, ["project", "list", "--source", "google", "--cursor", "opaque/token==", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["complete"] is None
    client.list_native_projects.assert_awaited_once_with(cursor="opaque/token==")


@pytest.mark.parametrize("extra", [["--limit", "21"], ["--cursor", "x" * 4097]])
def test_cli_native_projects_rejects_controls_before_profile(monkeypatch, extra):
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: pytest.fail("profile accessed"))
    result = CliRunner().invoke(main, ["project", "list", "--source", "google", *extra])
    assert result.exit_code == 2


def test_cli_native_media_read_only_snapshot(monkeypatch):
    client = _client(monkeypatch, cli_project)
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(
        main, ["project", "media", "--project", PROJECT, "--source", "google", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["media"] == []
    client.list_native_media.assert_awaited_once_with(PROJECT)


@pytest.mark.asyncio
async def test_mcp_native_projects_snapshot(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    result = await tools.gflow_list_projects(source="google", cursor="opaque")
    assert result["complete"] is None
    client.list_native_projects.assert_awaited_once_with(cursor="opaque")


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"limit": 21}, {"offset": 1}, {"cursor": "x" * 4097}])
async def test_mcp_native_projects_invalid_before_profile(monkeypatch, kwargs):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_list_projects(source="google", **kwargs)
    assert result["status"] == "error"
    assert result["error"]["status"] == 400


@pytest.mark.asyncio
async def test_mcp_native_media_snapshot(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    result = await tools.gflow_project_media(project=PROJECT)
    assert result["complete"] is None
    client.list_native_media.assert_awaited_once_with(PROJECT)


def test_cli_native_media_uuid_validation_before_profile(monkeypatch):
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: pytest.fail("profile accessed"))
    result = CliRunner().invoke(main, ["project", "media", "--project", "not-a-uuid"])
    assert result.exit_code == 2


@pytest.mark.asyncio
async def test_mcp_native_media_uuid_validation_before_profile(monkeypatch):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_project_media(project="not-a-uuid")
    assert result["status"] == "error"
    assert result["error"]["status"] == 400


def test_cli_native_projects_human_output_uses_native_name(monkeypatch):
    client = _client(monkeypatch, cli_project)
    client.list_native_projects.return_value = {
        **PROJECTS,
        "projects": [{"project_id": PROJECT, "name": "[bold]Native project name[/bold]"}],
        "returned_count": 1,
    }
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(main, ["project", "list", "--source", "google"])
    assert result.exit_code == 0, result.output
    assert PROJECT in result.output
    assert "[bold]Native project name[/bold]" in result.output
    assert "Snapshot completeness: unknown" in result.output
