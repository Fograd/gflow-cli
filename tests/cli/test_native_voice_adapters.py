from unittest.mock import AsyncMock, Mock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_character
from gflow_cli.cli import main
from gflow_cli.mcp import tools

PROJECT = "12345678-1234-1234-1234-123456789abc"


def test_google_voice_bad_project_before_profile(monkeypatch):
    resolve = Mock(side_effect=AssertionError("must not resolve"))
    monkeypatch.setattr(cli_character, "_resolve_profile", resolve)
    result = CliRunner().invoke(
        main, ["character", "voices", "--catalog", "google", "--project", "bad", "--json"]
    )
    assert result.exit_code != 0
    assert "UUID" in result.output
    resolve.assert_not_called()


def test_bundled_voice_project_cannot_be_silently_ignored():
    result = CliRunner().invoke(main, ["character", "voices", "--project", PROJECT])
    assert result.exit_code != 0
    assert "google" in result.output


@pytest.mark.asyncio
async def test_mcp_native_voice_invalid_project_before_profile(monkeypatch):
    resolve = Mock(side_effect=AssertionError("must not resolve"))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolve)
    result = await tools.gflow_character_voices(catalog="google", project="bad")
    assert result["status"] == "error"
    resolve.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_bundled_default_stays_offline(monkeypatch):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", Mock(side_effect=AssertionError("offline"))
    )
    result = await tools.gflow_character_voices()
    assert len(result["voices"]) == 30
    assert result["count"] == 30


def _native_client(monkeypatch, module):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.list_native_voices = AsyncMock(
        return_value={
            "voices": [
                {"name": "[red]Charon", "description": "[link=x]literal", "sample_url": None}
            ],
            "returned_count": 1,
            "complete": None,
            "scope": "native system presets",
        }
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(module, "FlowApiClient", lambda **kw: context)
    return client


def test_cli_google_voices_forwards_project_and_json_scope(monkeypatch):
    import json

    client = _native_client(monkeypatch, cli_character)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda _: "one")
    result = CliRunner().invoke(
        main, ["character", "voices", "--catalog", "google", "--project", PROJECT, "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["complete"] is None
    client.list_native_voices.assert_awaited_once_with(PROJECT)


def test_cli_google_voices_human_preserves_literal_markup(monkeypatch):
    _native_client(monkeypatch, cli_character)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda _: "one")
    result = CliRunner().invoke(
        main, ["character", "voices", "--catalog", "google", "--project", PROJECT]
    )
    assert result.exit_code == 0, result.output
    assert "[red]Charon" in result.output
    assert "[link=x]literal" in result.output


@pytest.mark.asyncio
async def test_mcp_google_voices_forwards_project(monkeypatch):
    client = _native_client(monkeypatch, tools)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "one")
    result = await tools.gflow_character_voices(catalog="google", project=PROJECT, profile="one")
    assert result["complete"] is None
    assert result["count"] == 1
    client.list_native_voices.assert_awaited_once_with(PROJECT)
