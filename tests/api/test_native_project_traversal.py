"""Bounded pagination is traversal evidence, never account deletion proof."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs as module
from gflow_cli.errors import ConfigurationError, WireFormatError

P = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"


def client():
    return SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value="page"),
        _checkin_page=Mock(),
    )


@pytest.mark.asyncio
async def test_two_pages_one_lease_exhaustion_is_not_complete_snapshot(monkeypatch):
    obj = client()
    operation = AsyncMock(
        side_effect=[
            {"projects": [{"project_id": P, "name": "One"}], "next_cursor": "opaque"},
            {"projects": [{"project_id": P2, "name": "Two"}], "next_cursor": None},
        ]
    )
    monkeypatch.setattr(module, "list_projects", operation)
    result = await module.projects_snapshot(obj, all_pages=True, max_pages=2)
    assert result["returned_count"] == 2 and result["pages_read"] == 2
    assert result["pagination_exhausted"] is True and result["complete"] is None
    assert [call.args for call in operation.await_args_list] == [("page", None), ("page", "opaque")]
    obj._checkout_page.assert_awaited_once()
    obj._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
async def test_page_cap_preserves_continuation_even_for_empty_page(monkeypatch):
    obj = client()
    monkeypatch.setattr(
        module, "list_projects", AsyncMock(return_value={"projects": [], "next_cursor": "next"})
    )
    result = await module.projects_snapshot(obj, "start", all_pages=True, max_pages=1)
    assert result["pagination_exhausted"] is False and result["next_cursor"] == "next"
    assert result["pages_read"] == 1 and result["returned_count"] == 0
    assert "continuation" in result["scope"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pages",
    [
        [{"projects": [], "next_cursor": "start"}],
        [
            {"projects": [{"project_id": P, "name": "One"}], "next_cursor": "next"},
            {"projects": [{"project_id": P, "name": "Again"}], "next_cursor": None},
        ],
        [
            {
                "projects": [{"project_id": P, "name": "One"}, {"project_id": P, "name": "Again"}],
                "next_cursor": None,
            }
        ],
    ],
)
async def test_cycles_or_duplicate_ids_refuse_and_release(monkeypatch, pages):
    obj = client()
    monkeypatch.setattr(module, "list_projects", AsyncMock(side_effect=pages))
    with pytest.raises(WireFormatError):
        await module.projects_snapshot(obj, "start", all_pages=True, max_pages=3)
    obj._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"all_pages": 1},
        {"all_pages": True, "max_pages": True},
        {"all_pages": True, "max_pages": 0},
        {"all_pages": True, "max_pages": 101},
        {"max_pages": 2},
    ],
)
async def test_bad_controls_refuse_before_checkout(kwargs):
    obj = client()
    with pytest.raises(ConfigurationError):
        await module.projects_snapshot(obj, **kwargs)
    obj._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_returns_single_page(monkeypatch):
    import asyncio

    obj = client()
    monkeypatch.setattr(module, "list_projects", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await module.projects_snapshot(obj, all_pages=True)
    obj._checkin_page.assert_called_once_with("page")
