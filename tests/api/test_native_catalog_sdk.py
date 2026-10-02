from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_catalogs as module
from gflow_cli.errors import ConfigurationError, WireFormatError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
V = "44444444-4444-4444-8444-444444444444"


def payload():
    image = [M, P, W, "SIGNED_URL", None, [], [None, None, [1024, 1024]]]
    video = [V, P, W, "SIGNED_URL", None, [], None, [None, [1280, 1280, [1]]]]
    return [None, [], [image, video]]


def test_measured_media_arms_dimensions_and_unknown_completeness():
    result = module.parse_media_snapshot(payload(), P)
    assert result["complete"] is None
    assert result["returned_count"] == 2
    assert result["media"] == [
        {
            "media_id": M,
            "project_id": P,
            "workflow_id": W,
            "kind": "image",
            "width": 1024,
            "height": 1024,
        },
        {
            "media_id": V,
            "project_id": P,
            "workflow_id": W,
            "kind": "video",
            "width": 1280,
            "height": 1280,
        },
    ]
    assert "SIGNED_URL" not in str(result)


def test_missing_dims_and_unknown_arms_are_not_guessed():
    data = payload()
    data[2][0][6] = []
    data[2][1][6] = []
    rows = module.parse_media_snapshot(data, P)["media"]
    assert rows[0]["kind"] == "image" and "width" not in rows[0]
    assert rows[1]["kind"] == "unknown"


@pytest.mark.parametrize("change", ["project", "media", "workflow", "duplicate"])
def test_bad_identity_or_duplicates_fail_closed(change):
    data = payload()
    if change == "duplicate":
        data[2].append(data[2][0])
    else:
        data[2][0][{"project": 1, "media": 0, "workflow": 2}[change]] = "bad"
    with pytest.raises(ValueError):
        module.parse_media_snapshot(data, P)


@pytest.mark.asyncio
async def test_projects_validate_cursor_before_checkout():
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.projects_snapshot(client, "x" * 4097)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_returns_page_even_parser_fails(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[None, [], []]))
    result = await module.media_snapshot(client, P)
    assert result["returned_count"] == 0
    client._checkin_page.assert_called_once_with(page)
    client._checkin_page.reset_mock()
    monkeypatch.setattr(
        module, "read_project_payload", AsyncMock(return_value=[None, [], [["bad"]]])
    )
    with pytest.raises(WireFormatError):
        await module.media_snapshot(client, P)
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_labs_override_refuses_without_page():
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="labs.google"), _checkout_page=AsyncMock()
    )
    with pytest.raises(ConfigurationError):
        await module.media_snapshot(client, P)
    client._checkout_page.assert_not_awaited()


@pytest.mark.parametrize("dims", [[True, 1], [-1, 10], [100001, 10], ["1024", 1024], None])
def test_bad_dimensions_are_omitted_without_guess(dims):
    data = payload()
    data[2][0][6][2] = dims
    assert "width" not in module.parse_media_snapshot(data, P)["media"][0]


@pytest.mark.parametrize("data", [None, [], [None, [], None], [None, [], [{}]]])
def test_unrecognized_collection_shape_is_error(data):
    with pytest.raises(ValueError):
        module.parse_media_snapshot(data, P)


@pytest.mark.asyncio
async def test_projects_transports_one_page_and_returns_cursor(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    operation = AsyncMock(
        return_value={"projects": [{"project_id": P, "name": "Name"}], "next_cursor": "opaque"}
    )
    monkeypatch.setattr(module, "list_projects", operation)
    result = await module.projects_snapshot(client, "previous")
    assert result["next_cursor"] == "opaque" and result["returned_count"] == 1
    assert result["complete"] is None
    operation.assert_awaited_once_with(page, "previous")
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_projects_rpc_failure_returns_page_without_retry(monkeypatch):
    page = object()
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    operation = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(module, "list_projects", operation)
    with pytest.raises(TimeoutError):
        await module.projects_snapshot(client)
    operation.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_media_invalid_project_before_checkout():
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.media_snapshot(client, "bad")
    client._checkout_page.assert_not_awaited()
