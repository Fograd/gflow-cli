"""Explicit pending projects are hydrated without skipping them via account cursors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs as module
from gflow_cli.errors import ConfigurationError, WireFormatError
from tests.api.transports.test_character_details import P, fixture

P2 = "99999999-9999-4999-8999-999999999999"


def client():
    return SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"catalog_project_ids": [P]},
        {"include_catalogs": True, "catalog_project_ids": []},
        {"include_catalogs": True, "catalog_project_ids": "bad"},
        {"include_catalogs": True, "catalog_project_ids": [P, P]},
        {"include_catalogs": True, "catalog_project_ids": ["bad"]},
        {"include_catalogs": True, "catalog_project_ids": [P], "cursor": "next"},
        {"include_catalogs": True, "catalog_project_ids": [P], "all_pages": True},
        {"include_catalogs": True, "catalog_project_ids": [P], "max_pages": 1},
        {"include_catalogs": True, "catalog_project_ids": [P] * 21},
    ],
)
async def test_invalid_resume_controls_precede_checkout(kwargs):
    c = client()
    with pytest.raises(ConfigurationError):
        await module.projects_snapshot(c, **kwargs)
    c._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_keeps_order_and_pending_ids_without_account_page(monkeypatch):
    c = client()
    listing = AsyncMock(side_effect=AssertionError("account listing must not run"))
    monkeypatch.setattr(module, "list_projects", listing)
    read = AsyncMock(return_value=fixture())
    monkeypatch.setattr(module, "read_project_payload", read)
    result = await module.projects_snapshot(
        c, include_catalogs=True, catalog_project_ids=[P, P2], max_projects=1
    )
    assert result["projects"] == [] and result["pages_read"] == 0
    assert result["pagination_exhausted"] is None and result["complete"] is None
    assert result["next_cursor"] is None and result["catalog_resume"] is True
    assert result["pending_project_ids"] == [P2] and result["catalogs_capped"] is True
    assert result["catalog_projects_read"] == 1 and result["project_catalogs"][0]["project_id"] == P
    read.assert_awaited_once_with("page", P, require_request_project=True, allow_empty_catalog=True)
    listing.assert_not_awaited()
    c._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_resume_rejects_foreign_catalog_rows_and_returns_page(monkeypatch):
    c = client()
    data = fixture()
    data[1][0][4] = P2
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=data))
    with pytest.raises(WireFormatError):
        await module.projects_snapshot(c, include_catalogs=True, catalog_project_ids=[P])
    c._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_resume_can_read_an_observed_empty_project(monkeypatch):
    c = client()
    monkeypatch.setattr(
        module, "read_project_payload", AsyncMock(return_value=[None, [], [], [], None, None])
    )
    result = await module.projects_snapshot(c, include_catalogs=True, catalog_project_ids=[P])
    assert result["project_catalogs"][0]["counts"] == {
        "media": 0,
        "workflows": 0,
        "characters": 0,
        "user_voices": 0,
    }
    assert result["catalog_projects_read"] == 1 and result["pending_project_ids"] == []
    assert result["catalogs_capped"] is False and result["pagination_exhausted"] is None
