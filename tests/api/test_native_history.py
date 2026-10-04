"""Measured account workflow history projection, without private media fields."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_history as module
from gflow_cli.errors import ConfigurationError, WireFormatError

P = "11111111-1111-4111-8111-111111111111"
W = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"
Q = "44444444-4444-4444-8444-444444444444"
V = "55555555-5555-4555-8555-555555555555"
N = "66666666-6666-4666-8666-666666666666"


def payload(cursor=None, project=P, workflow=W, media=M):
    return [
        [[workflow, None, None, ["private caption", [1, 2], None, None, media, Q, []], project]],
        cursor,
        [[media, project, workflow, None, None, ["private prompt"], [[], None, [1024, 1024]]]],
    ]


def test_parser_correlates_projects_and_strips_private_fields():
    result = module.parse_history_page(payload("opaque"))
    assert result["workflows"] == [{"workflow_id": W, "project_id": P, "primary_media_id": M}]
    assert result["media"][0] == {
        "media_id": M,
        "project_id": P,
        "workflow_id": W,
        "kind": "image",
        "generation_source": "unknown",
        "likely_upload": False,
        "width": 1024,
        "height": 1024,
    }
    assert result["next_cursor"] == "opaque"
    assert "private" not in repr(result)


@pytest.mark.parametrize(
    "fault",
    [
        "foreign-project",
        "unknown-workflow",
        "duplicate-workflow",
        "duplicate-media",
        "primary-conflict",
        "bad-shape",
        "bad-cursor",
    ],
)
def test_parser_refuses_invalid_relation_or_shape(fault):
    data = payload()
    if fault == "foreign-project":
        data[2][0][1] = Q
    elif fault == "unknown-workflow":
        data[2][0][2] = Q
    elif fault == "duplicate-workflow":
        data[0].append(data[0][0])
    elif fault == "duplicate-media":
        data[2].append(data[2][0])
    elif fault == "primary-conflict":
        other = payload(None, Q, V, N)
        data[0].extend(other[0])
        data[2].extend(other[2])
        data[0][0][3][4] = N
    elif fault == "bad-shape":
        data[2] = None
    else:
        data[1] = "token\n"
    with pytest.raises(ValueError):
        module.parse_history_page(data)


def test_media_free_workflow_is_observed_without_deletion_inference():
    data = payload()
    data[0][0][3][4] = None
    data[2] = []
    assert module.parse_history_page(data)["workflows"] == [{"workflow_id": W, "project_id": P}]


@pytest.mark.parametrize(
    "options",
    [
        {"all_pages": 1},
        {"max_pages": 1},
        {"all_pages": True, "max_pages": 51},
        {"all_pages": True, "max_pages": True},
        {"max_media": True},
        {"max_media": 1001},
        {"cursor": ""},
        {"cursor": "é"},
    ],
)
@pytest.mark.asyncio
async def test_controls_validate_before_checkout(options):
    client = SimpleNamespace(settings=SimpleNamespace(flow_host="auto"), _checkout_page=AsyncMock())
    with pytest.raises(ConfigurationError):
        await module.history_snapshot(client, **options)
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_pages_one_lease_exact_requests_and_honest_scope(monkeypatch):
    page = SimpleNamespace(url="https://flow.google.com/u/0/", wait_for_function=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    rpc = AsyncMock(side_effect=[payload("next"), payload(None, Q, V, N)])
    monkeypatch.setattr(module, "native_rpc", rpc)
    result = await module.history_snapshot(client, all_pages=True, max_pages=2)
    assert result["pages_read"] == 2 and result["pagination_exhausted"] is True
    assert result["complete"] is None and result["returned_count"] == 2
    assert rpc.call_args_list[0].args[2] == [20, None]
    assert rpc.call_args_list[1].args[2] == [20, "next"]
    assert all(call.kwargs == {"require_single": True} for call in rpc.call_args_list)
    client._checkout_page.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.parametrize("failure", ["cycle", "duplicate"])
@pytest.mark.asyncio
async def test_traversal_refuses_cycle_and_duplicate_ids(monkeypatch, failure):
    page = SimpleNamespace(url="https://flow.google.com/u/0/", wait_for_function=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    second = payload("next", Q, V, N) if failure == "cycle" else payload(None)
    monkeypatch.setattr(module, "native_rpc", AsyncMock(side_effect=[payload("next"), second]))
    with pytest.raises(WireFormatError):
        await module.history_snapshot(client, all_pages=True, max_pages=2)
    client._checkin_page.assert_called_once()


@pytest.mark.asyncio
async def test_cap_keeps_last_completed_page_and_resume_cursor(monkeypatch):
    page = SimpleNamespace(url="https://flow.google.com/u/0/", wait_for_function=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(
        module, "native_rpc", AsyncMock(side_effect=[payload("next"), payload(None, Q, V, N)])
    )
    result = await module.history_snapshot(client, all_pages=True, max_pages=2, max_media=1)
    assert result["returned_count"] == 1 and result["next_cursor"] == "next"
    assert result["capped"] is True and result["pagination_exhausted"] is False


def test_project_history_controls_are_normalized_before_browser():
    assert module.validate_project_history_options(False, None, None, None) == (None, None, None)
    assert module.validate_project_history_options(True, None, None, None) == (None, 50, 1000)
    assert module.validate_project_history_options(True, "opaque", 2, 20) == ("opaque", 2, 20)
    with pytest.raises(ValueError):
        module.validate_project_history_options(False, "opaque", None, None)


def test_page_size_and_canonical_duplicate_identity_refuse():
    data = payload()
    data[0] = data[0] * 21
    with pytest.raises(ValueError):
        module.parse_history_page(data)
    data = payload()
    duplicate = list(data[2][0])
    duplicate[0] = M.upper()
    data[2].append(duplicate)
    with pytest.raises(ValueError):
        module.parse_history_page(data)


@pytest.mark.asyncio
async def test_timeout_returns_only_completed_verified_page(monkeypatch):
    import asyncio

    page = SimpleNamespace(url="https://flow.google.com/u/0/", wait_for_function=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    calls = 0

    async def rpc(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return payload("next")
        await asyncio.sleep(1)

    monkeypatch.setattr(module, "native_rpc", rpc)
    monkeypatch.setattr(module, "HISTORY_TIMEOUT_SECONDS", 0.01)
    result = await module.history_snapshot(client, all_pages=True, max_pages=2)
    assert result["timed_out"] is True and result["pages_read"] == 1
    assert result["next_cursor"] == "next" and result["complete"] is None
    assert result["pagination_exhausted"] is False
    client._checkin_page.assert_called_once()


def test_missing_primary_is_unverified_not_cross_owned_and_preserves_raw_count(tmp_path):
    from uuid import UUID

    from gflow_cli.selfhost.native_observations import NativeObservationStore

    workflows = []
    media = []
    for index in range(20):
        workflow = str(UUID(int=100 + index, version=4))
        identifier = str(UUID(int=200 + index, version=4))
        workflows.append([workflow, None, None, [None, None, None, None, identifier], P])
        if index < 19:
            media.append([identifier, P, workflow, None, None, None, [[["synthetic"]]]])
    result = module.parse_history_page([workflows, "opaque-next", media])
    assert len(result["workflows"]) == 20 and len(result["media"]) == 19
    assert result["media_scanned_count"] == 19
    assert "primary_media_id" not in result["workflows"][-1]
    assert all("primary_media_id" in row for row in result["workflows"][:-1])
    counts = NativeObservationStore(tmp_path).merge_history("pro1", "one", result)
    assert counts["workflows"] == 20 and counts["media"] == 19
    assert counts["complete"] is None


def test_missing_primary_still_requires_well_formed_uuid():
    data = payload()
    data[0][0][3][4] = "malformed"
    data[2] = []
    with pytest.raises(ValueError):
        module.parse_history_page(data)
