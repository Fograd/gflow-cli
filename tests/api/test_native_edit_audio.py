"""Native edit audio ownership: uploaded media need not be saved-TTS visible."""

from copy import deepcopy

import pytest

from gflow_cli.api.native_video_edit import validate_edit_audio
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
A = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"


def fixture(saved=False):
    metadata = [None] * 10
    metadata[9] = 1 if saved else None
    audio = [
        A,
        P,
        W,
        None,
        None,
        metadata,
        None,
        None,
        None,
        None,
        [[None, "performance", None, None, None, None, "dialogue"]],
    ]
    return [None, [[W, None, None, ["audio", None, None, None, A], P]], [audio]]


@pytest.mark.parametrize("saved", [False, True])
def test_active_owned_audio_without_saved_visibility_is_supported(saved):
    validate_edit_audio(fixture(saved), P, (A,))


def test_owned_batch_sibling_does_not_need_primary_identity():
    payload = fixture()
    payload[1][0][3][4] = OTHER
    validate_edit_audio(payload, P, (A,))


@pytest.mark.parametrize(
    "case",
    [
        "foreign_media",
        "foreign_workflow",
        "wrong_workflow",
        "archived",
        "duplicate_media",
        "duplicate_workflow",
        "mixed_image",
        "malformed_video",
        "empty_audio",
        "empty_sample",
        "missing",
        "preset",
    ],
)
def test_ambiguous_or_unowned_audio_refuses(case):
    payload = fixture()
    refs = (A,)
    if case == "foreign_media":
        payload[2][0][1] = OTHER
    elif case == "foreign_workflow":
        payload[1][0][4] = OTHER
    elif case == "wrong_workflow":
        payload[2][0][2] = OTHER
    elif case == "archived":
        payload[1][0][3][2] = 1
    elif case == "duplicate_media":
        payload[2].append(deepcopy(payload[2][0]))
    elif case == "duplicate_workflow":
        payload[1].append(deepcopy(payload[1][0]))
    elif case == "mixed_image":
        payload[2][0][6] = []
    elif case == "malformed_video":
        payload[2][0][7] = "invalid"
    elif case == "empty_audio":
        payload[2][0][10] = []
    elif case == "empty_sample":
        payload[2][0][10] = [[]]
    elif case == "missing":
        payload[2] = []
    elif case == "preset":
        refs = ("voices/charon",)
    with pytest.raises(ConfigurationError):
        validate_edit_audio(payload, P, refs)


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [False, True])
async def test_generic_audio_reaches_existing_single_dispatch(monkeypatch, saved):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_video_edit as module
    from gflow_cli.api.native_extension import new_extension_started

    payload = fixture(saved)
    source = OTHER
    source_workflow = "55555555-5555-4555-8555-555555555555"
    payload[1].append([source_workflow, None, None, ["video", None, None, None, source], P])
    payload[2].append([source, P, source_workflow, None, None, None, None, [None, [160, 90]]])
    started = new_extension_started(P, source, 1)
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "new_extension_started", lambda *_: started)
    read = AsyncMock(return_value=payload)
    monkeypatch.setattr(module, "read_project_payload", read)
    usage = [None] * 25
    usage[0] = "edit-key"
    usage[21] = [3, 2, 5]
    monkeypatch.setattr(
        module,
        "_read_native",
        AsyncMock(
            side_effect=[[[None, None, None, None, [["Omni", [usage]]]]], [None, None, None, 1]]
        ),
    )
    monkeypatch.setattr(
        module, "parse_extension_models", lambda *_, **__: [{"model_key": "edit-key"}]
    )
    mint = AsyncMock(return_value="test")
    monkeypatch.setattr(module, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    monkeypatch.setattr(module, "rpc_errors", lambda _: [])
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda _: [
            ("jIps6", [None, None, None, [[started.media_ids[0], P, started.workflow_ids[0]]]])
        ],
    )
    checkpoint = AsyncMock()
    result = await module.edit_native_video(
        client,
        project_id=P,
        media_id=source,
        prompt="edit",
        model_key="edit-key",
        end_frame=120,
        audio_ids=(A,),
        on_started=checkpoint,
    )
    assert result.media_ids == started.media_ids
    read.assert_awaited_once_with(page, P)
    mint.assert_awaited_once_with("VIDEO_GENERATION")
    checkpoint.assert_awaited_once_with(result)
    page.evaluate.assert_awaited_once()
    assert page.evaluate.call_args.args[1]["args"][0][0][9] == [[A]]
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_invalid_audio_refuses_before_mint_or_checkpoint(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_video_edit as module

    payload = fixture()
    source = OTHER
    source_workflow = "55555555-5555-4555-8555-555555555555"
    payload[1].append([source_workflow, None, None, ["video", None, None, None, source], P])
    payload[2].append([source, P, source_workflow, None, None, None, None, [None, [160, 90]]])
    payload[2][0][7] = "malformed"
    page = SimpleNamespace(evaluate=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload))
    minter = Mock()
    monkeypatch.setattr(module, "TokenMinter", minter)
    checkpoint = AsyncMock()
    with pytest.raises(ConfigurationError):
        await module.edit_native_video(
            client,
            project_id=P,
            media_id=source,
            prompt="edit",
            model_key="edit-key",
            end_frame=120,
            audio_ids=(A,),
            on_started=checkpoint,
        )
    minter.assert_not_called()
    checkpoint.assert_not_awaited()
    page.evaluate.assert_not_awaited()
    client._checkin_page.assert_called_once_with(page)
