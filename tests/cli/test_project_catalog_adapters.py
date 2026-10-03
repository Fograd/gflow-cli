"""Catalog controls must survive public adapter/private worker boundaries."""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from gflow_cli import cli_project
from gflow_cli.cli import main
from gflow_cli.mcp import tools
from gflow_cli.selfhost.server import create_app
from tests.cli.test_native_catalog_adapters import _client
from tests.cli.test_project_traversal_adapters import cfg


def test_cli_catalog_forwarding(monkeypatch):
    client = _client(monkeypatch, cli_project)
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(
        main,
        [
            "project",
            "list",
            "--source",
            "google",
            "--include-catalogs",
            "--max-projects",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    client.list_native_projects.assert_awaited_once_with(
        cursor=None, all_pages=False, max_pages=None, include_catalogs=True, max_projects=1
    )


@pytest.mark.asyncio
async def test_mcp_catalog_forwarding(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    await tools.gflow_list_projects(source="google", include_catalogs=True, max_projects=1)
    client.list_native_projects.assert_awaited_once_with(
        cursor=None, all_pages=False, max_pages=None, include_catalogs=True, max_projects=1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "local", "include_catalogs": True},
        {"source": "google", "max_projects": 1},
        {"source": "google", "include_catalogs": True, "max_projects": True},
    ],
)
async def test_mcp_catalog_controls_precede_profile(monkeypatch, kwargs):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_list_projects(**kwargs)
    assert result["status"] == "error"


def test_rest_catalog_forwarding(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(
            {
                "status": "ok",
                "projects": [],
                "next_cursor": None,
                "project_catalogs": [],
                "catalog_projects_read": 0,
                "catalog_counts": {},
                "pending_project_ids": [],
                "catalogs_capped": False,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params={"source": "google", "includeCatalogs": "true", "maxProjects": "1"},
            headers={"Authorization": "Bearer test"},
        )
    assert result.status_code == 200
    assert json.loads(calls[0][0][5]) == {
        "cursor": None,
        "include_catalogs": True,
        "max_projects": 1,
    }
    assert calls[0][1] >= 210
    assert result.json()["catalogProjectsRead"] == 0 and result.json()["pendingProjectIds"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"source": "local", "includeCatalogs": "true"},
        {"source": "google", "maxProjects": "1"},
        {"source": "google", "includeCatalogs": "yes"},
        {"source": "google", "includeCatalogs": "true", "maxProjects": "21"},
    ],
)
def test_rest_catalog_controls_do_not_dispatch(tmp_path, monkeypatch, params):
    async def run(*args):
        pytest.fail("browser dispatched")

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params=params,
            headers={"Authorization": "Bearer test"},
        )
    assert result.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"all_pages": 1},
        {"max_pages": True},
        {"include_catalogs": "true"},
        {"include_catalogs": 1},
        {"max_projects": True},
        {"max_projects": "1"},
    ],
)
def test_registered_mcp_model_rejects_coerced_catalog_controls(payload):
    from pydantic import ValidationError

    tool = tools.server._tool_manager.get_tool("gflow_list_projects")
    with pytest.raises(ValidationError):
        tool.fn_metadata.arg_model.model_validate(payload)
