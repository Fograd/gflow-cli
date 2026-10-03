import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_assets
from gflow_cli.errors import ConfigurationError, WireFormatError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def client():
    return SimpleNamespace(
        settings=SimpleNamespace(flow_host="flow.google.com"),
        _checkout_page=AsyncMock(return_value=object()),
        _checkin_page=Mock(),
    )


@pytest.mark.asyncio
async def test_checkout_timeout_is_typed_without_checkin():
    value = client()
    value._checkout_page.side_effect = TimeoutError()
    with pytest.raises(WireFormatError):
        await native_assets.get_native_asset(value, P, M)
    value._checkin_page.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_read_releases_once(monkeypatch):
    value = client()
    monkeypatch.setattr(
        native_assets, "lookup_asset", AsyncMock(side_effect=asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        await native_assets.get_native_asset(value, P, M)
    value._checkin_page.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_cancelled_read(monkeypatch):
    value = client()
    value._checkin_page.side_effect = RuntimeError()
    monkeypatch.setattr(
        native_assets, "lookup_asset", AsyncMock(side_effect=asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        await native_assets.get_native_asset(value, P, M)
    value._checkin_page.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,error", [(FileExistsError(), ConfigurationError), (OSError(), WireFormatError)]
)
async def test_output_error_remains_typed(monkeypatch, tmp_path, failure, error):
    monkeypatch.setattr(native_assets, "get_native_asset", AsyncMock(return_value=object()))
    monkeypatch.setattr(native_assets, "download_asset", AsyncMock(side_effect=failure))
    with pytest.raises(error):
        await native_assets.download_native_asset(client(), P, M, tmp_path)
