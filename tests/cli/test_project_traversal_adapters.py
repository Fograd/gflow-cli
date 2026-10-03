"""Traversal controls must reach each public adapter before browser access."""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from gflow_cli import cli_project
from gflow_cli.cli import main
from gflow_cli.mcp import tools
from gflow_cli.selfhost.server import Settings, create_app
from tests.cli.test_native_catalog_adapters import _client

P = "11111111-1111-4111-8111-111111111111"


def test_cli_traversal_forwarding(monkeypatch):
    client = _client(monkeypatch, cli_project)
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(
        main, ["project", "list", "--source", "google", "--all-pages", "--max-pages", "2", "--json"]
    )
    assert result.exit_code == 0, result.output
    client.list_native_projects.assert_awaited_once_with(cursor=None, all_pages=True, max_pages=2)


@pytest.mark.asyncio
async def test_mcp_traversal_forwarding(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    await tools.gflow_list_projects(source="google", all_pages=True, max_pages=2)
    client.list_native_projects.assert_awaited_once_with(cursor=None, all_pages=True, max_pages=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "local", "all_pages": True},
        {"source": "google", "max_pages": 2},
        {"source": "google", "all_pages": True, "max_pages": True},
    ],
)
async def test_mcp_invalid_controls_precede_profile(monkeypatch, kwargs):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_list_projects(**kwargs)
    assert result["status"] == "error"


def cfg(root):
    return Settings(
        token="test",
        root=root,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )


def test_rest_traversal_forwarding(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(
            {
                "status": "ok",
                "projects": [],
                "next_cursor": "opaque",
                "returned_count": 0,
                "pages_read": 2,
                "pagination_exhausted": False,
                "complete": None,
                "scope": "bounded traversal",
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params={"source": "google", "allPages": "true", "maxPages": "2"},
            headers={"Authorization": "Bearer test"},
        )
    assert result.status_code == 200
    assert json.loads(calls[0][0][5]) == {"cursor": None, "all_pages": True, "max_pages": 2}
    assert calls[0][1] >= 210
    assert result.json()["pagesRead"] == 2 and result.json()["paginationExhausted"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"source": "local", "allPages": "true"},
        {"source": "google", "maxPages": "2"},
        {"source": "google", "allPages": "yes"},
        {"source": "google", "allPages": "true", "maxPages": "101"},
    ],
)
def test_rest_invalid_controls_never_dispatch(tmp_path, monkeypatch, params):
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
