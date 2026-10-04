"""CLI/direct MCP native sync controls reach the same scoped service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_inventory_sync as cli
from gflow_cli.cli import main
from gflow_cli.mcp import tools
from gflow_cli.services import inventory_sync


def configure(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        home=tmp_path,
        headless=True,
        profile_subdir=lambda profile: tmp_path / ("profile_" + profile),
    )
    cm = AsyncMock()
    cm.__aenter__.return_value = "native-client"
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_resolve_profile", lambda profile: "owned")
    monkeypatch.setattr(cli, "read_account_file", lambda path: "account@example.test")
    monkeypatch.setattr(cli, "FlowApiClient", lambda **kwargs: cm)
    monkeypatch.setattr(tools, "get_settings", lambda: settings)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "owned")
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: cm)
    monkeypatch.setattr(
        "gflow_cli.profile_store.read_account_file", lambda path: "account@example.test"
    )
    sync = AsyncMock(return_value={"complete": None, "traversal_finished": False})
    monkeypatch.setattr(cli, "sync_native_inventory", sync)
    monkeypatch.setattr(inventory_sync, "sync_native_inventory", sync)
    return sync, cm


def test_cli_sync_forwards_private_home_account_and_controls(monkeypatch, tmp_path):
    sync, _ = configure(monkeypatch, tmp_path)
    result = CliRunner().invoke(
        main,
        [
            "project",
            "sync",
            "--profile",
            "owned",
            "--max-steps",
            "3",
            "--max-seconds",
            "7",
            "--restart",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    sync.assert_awaited_once_with(
        "native-client",
        tmp_path / "native_inventory",
        profile="owned",
        account="account@example.test",
        max_steps=3,
        max_seconds=7,
        restart=True,
    )
    assert '"complete": null' in result.output


@pytest.mark.asyncio
async def test_direct_mcp_sync_forwards_same_controls(monkeypatch, tmp_path):
    sync, _ = configure(monkeypatch, tmp_path)
    result = await tools.gflow_sync_native_inventory(
        profile="owned", max_steps=3, max_seconds=7, restart=True
    )
    assert result == {"status": "ok", "complete": None, "traversal_finished": False}
    sync.assert_awaited_once_with(
        "native-client",
        tmp_path / "native_inventory",
        profile="owned",
        account="account@example.test",
        max_steps=3,
        max_seconds=7,
        restart=True,
    )


@pytest.mark.asyncio
async def test_mcp_invalid_bounds_precede_browser(monkeypatch, tmp_path):
    sync, cm = configure(monkeypatch, tmp_path)
    result = await tools.gflow_sync_native_inventory(max_steps=True)
    assert result["status"] == "error"
    sync.assert_not_awaited()
    cm.__aenter__.assert_not_awaited()


def test_cli_missing_recorded_account_refuses_browser(monkeypatch, tmp_path):
    sync, cm = configure(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "read_account_file", lambda path: None)
    result = CliRunner().invoke(main, ["project", "sync", "--json"])
    assert result.exit_code == 11
    sync.assert_not_awaited()
    cm.__aenter__.assert_not_awaited()
