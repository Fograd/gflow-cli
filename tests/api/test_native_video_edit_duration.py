"""Source-derived duration/default edit window, no billed calls."""

import pytest

from gflow_cli.api.native_video_edit import resolve_edit_window, source_video_duration
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def payload(duration):
    row = [M, P, W, None, None, None, None, [None, [160, 90, duration]]]
    return [None, None, [row]]


@pytest.mark.parametrize(
    "value,expected", [([2, 500000000], 2.5), (["8", 0], 8), ([0, 50000000], 0.05)]
)
def test_duration_actual_proto(value, expected):
    assert source_video_duration(payload(value), P, M) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        [True, 0],
        ["NaN", 0],
        [1, 1000000000],
        [-1, 0],
        [0, 0],
        [1, False],
        [1.5, 0],
        ["1.5", 0],
    ],
)
def test_duration_invalid_not_ui_fallback(value):
    with pytest.raises(ConfigurationError):
        source_video_duration(payload(value), P, M)


def test_duration_refuses_foreign_duplicate_and_nonexclusive():
    data = payload([8])
    data[2][0][1] = W
    with pytest.raises(ConfigurationError):
        source_video_duration(data, P, M)
    data = payload([8])
    data[2].append(data[2][0])
    with pytest.raises(ConfigurationError):
        source_video_duration(data, P, M)
    data = payload([8])
    data[2][0][6] = []
    with pytest.raises(ConfigurationError):
        source_video_duration(data, P, M)


@pytest.mark.parametrize(
    "duration,start,expected", [(2.51, 0, 60), (8, 24, 192), (12, 0, 240), (0.05, 0, 1)]
)
def test_derived_window_floor_and_cap(duration, start, expected):
    assert resolve_edit_window(duration, start, None) == expected


@pytest.mark.parametrize(
    "duration,start", [(0, 0), (float("nan"), 0), (0.01, 0), (1, 24), (True, 0), (10**500, 0)]
)
def test_unknown_short_or_empty_window_refuses(duration, start):
    with pytest.raises(ConfigurationError):
        resolve_edit_window(duration, start, None)


def test_explicit_end_is_preserved_without_duration():
    assert resolve_edit_window(None, 24, 120) == 120


@pytest.mark.asyncio
@pytest.mark.parametrize("measured,expected", [([2, 500000000], 60), (None, None)])
async def test_omitted_end_resolves_before_mint_and_single_submit(monkeypatch, measured, expected):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_video_edit as module
    from gflow_cli.api.native_extension import new_extension_started

    started = new_extension_started(P, M, 1)
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "new_extension_started", lambda *_: started)
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload(measured)))
    monkeypatch.setattr(module, "project_media", lambda *_: [{"media_id": M, "archived": False}])
    monkeypatch.setattr(module, "_read_native", AsyncMock(return_value=[None, None, None, 1]))
    monkeypatch.setattr(module, "parse_extension_models", lambda *_, **__: [{"model_key": "edit"}])
    mint = AsyncMock(return_value="private-test-token")
    minter = Mock(return_value=SimpleNamespace(mint=mint))
    monkeypatch.setattr(module, "TokenMinter", minter)
    monkeypatch.setattr(module, "rpc_errors", lambda _: [])
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda _: [
            ("jIps6", [None, None, None, [[started.media_ids[0], P, started.workflow_ids[0]]]])
        ],
    )
    if expected is None:
        with pytest.raises(ConfigurationError):
            await module.edit_native_video(
                client, project_id=P, media_id=M, prompt="edit", model_key="edit"
            )
        minter.assert_not_called()
        page.evaluate.assert_not_called()
    else:
        result = await module.edit_native_video(
            client, project_id=P, media_id=M, prompt="edit", model_key="edit"
        )
        assert result.end_frame == expected
        assert result.source_duration_seconds == 2.5
        assert page.evaluate.call_args.args[1]["args"][0][0][0] == [None, M, 0, expected]
        page.evaluate.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)
