from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs
from gflow_cli.errors import ConfigurationError, WireFormatError

PROJECT = "12345678-1234-1234-1234-123456789abc"


@pytest.mark.asyncio
async def test_native_voice_snapshot_returns_explicit_scope_and_returns_page(monkeypatch):
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )
    reader = AsyncMock(return_value=[])
    monkeypatch.setattr(native_catalogs, "read_project_payload", reader)
    monkeypatch.setattr(
        native_catalogs,
        "parse_native_voices",
        lambda _: [{"voice": "Charon", "description": "Informative", "source": "system"}],
    )
    result = await native_catalogs.voices_snapshot(client, PROJECT)
    assert result["voices"] == [
        {"name": "Charon", "description": "Informative", "sample_url": None, "source": "system"}
    ]
    assert result["complete"] is None
    assert result["catalog"] == "google"
    assert result["returned_count"] == 1
    reader.assert_awaited_once_with("page", PROJECT)
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_invalid_project_fails_before_checkout():
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await native_catalogs.voices_snapshot(client, "not-a-project")
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_parser_failure_returns_page_and_safe_problem(monkeypatch):
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(native_catalogs, "read_project_payload", AsyncMock(return_value=[]))

    def bad(_):
        raise ValueError("private-cookie")

    monkeypatch.setattr(native_catalogs, "parse_native_voices", bad)
    with pytest.raises(WireFormatError) as error:
        await native_catalogs.voices_snapshot(client, PROJECT)
    assert "private-cookie" not in str(error.value)
    client._checkin_page.assert_called_once_with("page")
