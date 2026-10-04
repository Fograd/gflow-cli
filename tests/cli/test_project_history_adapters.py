"""History controls mirror native project reads without changing default kwargs."""

import pytest
from click.testing import CliRunner

from gflow_cli import cli_project
from gflow_cli.api.client import FlowApiClient
from gflow_cli.cli import main
from gflow_cli.mcp import tools
from tests.cli.test_native_catalog_adapters import _client


def test_cli_history_forwarding(monkeypatch):
    client = _client(monkeypatch, cli_project)
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: "one")
    result = CliRunner().invoke(
        main,
        [
            "project",
            "list",
            "--source",
            "google",
            "--include-history",
            "--history-cursor",
            "opaque",
            "--history-max-pages",
            "2",
            "--history-max-media",
            "40",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    client.list_native_projects.assert_awaited_once_with(
        cursor=None,
        all_pages=False,
        max_pages=None,
        include_catalogs=False,
        max_projects=None,
        include_history=True,
        history_cursor="opaque",
        history_max_pages=2,
        history_max_media=40,
    )


@pytest.mark.asyncio
async def test_mcp_history_forwarding(monkeypatch):
    client = _client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    await tools.gflow_list_projects(
        source="google",
        include_history=True,
        history_cursor="opaque",
        history_max_pages=2,
        history_max_media=40,
    )
    client.list_native_projects.assert_awaited_once_with(
        cursor=None,
        all_pages=False,
        max_pages=None,
        include_catalogs=False,
        max_projects=None,
        include_history=True,
        history_cursor="opaque",
        history_max_pages=2,
        history_max_media=40,
    )


@pytest.mark.parametrize(
    "flags",
    [
        ["--include-history"],
        ["--source", "google", "--history-max-pages", "2"],
        ["--source", "google", "--include-history", "--history-max-media", "1001"],
    ],
)
def test_cli_invalid_history_controls_do_not_access_profile(monkeypatch, flags):
    monkeypatch.setattr(cli_project, "_resolve_profile", lambda p: pytest.fail("profile accessed"))
    assert CliRunner().invoke(main, ["project", "list", *flags]).exit_code != 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"include_history": True},
        {"source": "google", "history_cursor": "opaque"},
        {"source": "google", "include_history": True, "history_max_pages": True},
        {"source": "google", "include_history": True, "history_max_media": 1001},
    ],
)
async def test_mcp_invalid_history_controls_do_not_access_profile(monkeypatch, kwargs):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda p: pytest.fail("profile accessed")
    )
    result = await tools.gflow_list_projects(**kwargs)
    assert result["status"] == "error"


@pytest.mark.parametrize(
    "payload", [{"include_history": 1}, {"history_max_pages": "2"}, {"history_max_media": True}]
)
def test_registered_mcp_model_rejects_history_coercion(payload):
    from pydantic import ValidationError

    tool = tools.server._tool_manager.get_tool("gflow_list_projects")
    with pytest.raises(ValidationError):
        tool.fn_metadata.arg_model.model_validate(payload)


@pytest.mark.asyncio
async def test_sdk_history_controls_forward_and_default_remains_unchanged(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_catalogs

    operation = AsyncMock(return_value={})
    monkeypatch.setattr(native_catalogs, "projects_snapshot", operation)
    client = object.__new__(FlowApiClient)
    await client.list_native_projects(
        include_history=True, history_cursor="opaque", history_max_pages=2, history_max_media=40
    )
    operation.assert_awaited_once_with(
        client,
        None,
        all_pages=False,
        max_pages=None,
        include_catalogs=False,
        max_projects=None,
        include_history=True,
        history_cursor="opaque",
        history_max_pages=2,
        history_max_media=40,
    )
    operation.reset_mock()
    await client.list_native_projects()
    operation.assert_awaited_once_with(
        client, None, all_pages=False, max_pages=None, include_catalogs=False, max_projects=None
    )


@pytest.mark.asyncio
async def test_sdk_standalone_history_delegates_bounded_read(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_history

    operation = AsyncMock(return_value={"complete": None})
    monkeypatch.setattr(native_history, "history_snapshot", operation)
    client = object.__new__(FlowApiClient)
    result = await client.list_native_history("opaque", all_pages=True, max_pages=2, max_media=40)
    operation.assert_awaited_once_with(client, "opaque", all_pages=True, max_pages=2, max_media=40)
    assert result["complete"] is None
