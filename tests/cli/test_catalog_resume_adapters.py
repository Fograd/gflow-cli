"""Explicit catalog resume reaches all existing read-only adapters."""

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

P = "11111111-1111-4111-8111-111111111111"
P2 = "99999999-9999-4999-8999-999999999999"


def test_cli_resume_forwarding(monkeypatch):
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
            "--catalog-project-id",
            P,
            "--catalog-project-id",
            P2,
            "--max-projects",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    client.list_native_projects.assert_awaited_once_with(
        cursor=None,
        all_pages=False,
        max_pages=None,
        include_catalogs=True,
        max_projects=1,
        catalog_project_ids=[P, P2],
    )


@pytest.mark.asyncio
async def test_mcp_resume_forwarding(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    await tools.gflow_list_projects(
        source="google", include_catalogs=True, max_projects=1, catalog_project_ids=[P, P2]
    )
    client.list_native_projects.assert_awaited_once_with(
        cursor=None,
        all_pages=False,
        max_pages=None,
        include_catalogs=True,
        max_projects=1,
        catalog_project_ids=[P, P2],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "local", "include_catalogs": True, "catalog_project_ids": [P]},
        {"source": "google", "catalog_project_ids": [P]},
        {"source": "google", "include_catalogs": True, "catalog_project_ids": [P, P]},
        {
            "source": "google",
            "include_catalogs": True,
            "catalog_project_ids": [P],
            "all_pages": True,
        },
    ],
)
async def test_mcp_invalid_resume_precedes_profile(monkeypatch, kwargs):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_list_projects(**kwargs)
    assert result["status"] == "error"


def test_rest_resume_forwarding_and_empty_project_observation(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(
            {
                "status": "ok",
                "projects": [],
                "next_cursor": None,
                "returned_count": 0,
                "pages_read": 0,
                "pagination_exhausted": None,
                "catalog_resume": True,
                "project_catalogs": [{"project_id": P, "characters": [], "user_voices": []}],
                "catalog_projects_read": 1,
                "catalog_counts": {},
                "pending_project_ids": [P2],
                "catalogs_capped": True,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params={
                "source": "google",
                "includeCatalogs": "true",
                "maxProjects": "1",
                "catalogProjectIds": P + "," + P2,
            },
            headers={"Authorization": "Bearer test"},
        )
    assert result.status_code == 200, result.json()
    payload = json.loads(calls[0][0][5])
    assert payload["catalog_project_ids"] == [P, P2]
    assert result.json()["paginationExhausted"] is None and result.json()["pagesRead"] == 0
    assert result.json()["catalogResume"] is True
    assert result.json()["inventoryObservations"]["projects"] == 1
    assert result.json()["inventoryObservations"]["characters"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"source": "google", "catalogProjectIds": P},
        {"source": "local", "includeCatalogs": "true", "catalogProjectIds": P},
        {"source": "google", "includeCatalogs": "true", "catalogProjectIds": ""},
        {"source": "google", "includeCatalogs": "true", "catalogProjectIds": P + "," + P},
        {"source": "google", "includeCatalogs": "true", "catalogProjectIds": P, "cursor": "next"},
        {"source": "google", "includeCatalogs": "true", "catalogProjectIds": P, "allPages": "true"},
    ],
)
def test_rest_invalid_resume_precedes_worker(tmp_path, monkeypatch, params):
    async def run(*args):
        pytest.fail("worker dispatched")

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params=params,
            headers={"Authorization": "Bearer test"},
        )
    assert result.status_code == 422
