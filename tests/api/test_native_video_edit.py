"""Source-derived E4a edit DTO; no billed calls."""

import pytest

from gflow_cli.api.native_extension import new_extension_started
from gflow_cli.api.native_video_edit import video_edit_args
from gflow_cli.errors import ConfigurationError

S = new_extension_started(
    "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", 1
)


def test_exact_edit_dto_metadata_not_extension_position():
    args = video_edit_args(
        S,
        prompt="edit this",
        model_key="explicit-edit-key",
        aspect="16:9",
        token="test",
        start_frame=24,
        end_frame=120,
    )
    row = args[0][0]
    assert row[0] == [None, S.source_media_id, 24, 120]
    assert row[1] == [None, None, [[["edit this"]]]]
    assert row[2:4] == ["explicit-edit-key", 2]
    assert row[4] == [None, None, None, None, S.media_seeds[0], S.workflow_seeds[0]]
    assert args[1][5] == S.project_id


@pytest.mark.parametrize("start,end", [(-1, 24), (0, 241), (239, 239), (True, 24), (0, False)])
def test_bad_virtual_frame_range_refuses(start, end):
    with pytest.raises(ConfigurationError):
        video_edit_args(
            S,
            prompt="edit",
            model_key="explicit-edit-key",
            aspect="16:9",
            token="test",
            start_frame=start,
            end_frame=end,
        )


def test_extra_reference_positions_and_caps():
    image = "55555555-5555-4555-8555-555555555555"
    audio = "66666666-6666-4666-8666-666666666666"
    row = video_edit_args(
        S,
        prompt="edit",
        model_key="explicit-edit-key",
        aspect="9:16",
        token="test",
        image_ids=(image,),
        audio_ids=(audio,),
    )[0][0]
    assert row[8] == [[None, image]]
    assert row[9] == [[audio]]
    assert row[3] == 1
    with pytest.raises(ConfigurationError):
        video_edit_args(
            S,
            prompt="edit",
            model_key="explicit-edit-key",
            aspect="16:9",
            token="test",
            image_ids=(image,) * 6,
        )


@pytest.mark.asyncio
async def test_inactive_input_refuses_before_mint(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_video_edit as module

    page = SimpleNamespace(evaluate=AsyncMock())
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "parse_media_snapshot", lambda *_: {"media": []})
    monkeypatch.setattr(module, "project_media", lambda *_: [])
    minter = Mock()
    monkeypatch.setattr(module, "TokenMinter", minter)
    with pytest.raises(ConfigurationError):
        await module.edit_native_video(
            client,
            project_id=S.project_id,
            media_id=S.source_media_id,
            prompt="edit",
            model_key="explicit-edit-key",
            end_frame=120,
        )
    minter.assert_not_called()
    page.evaluate.assert_not_called()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_dimensions", [False, True])
async def test_dispatch_once_correlates_assigned_ids(monkeypatch, missing_dimensions):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_video_edit as module
    from gflow_cli.api.native_video_upscale import PromotionSource

    measured = AsyncMock(return_value=PromotionSource("video", S.workflow_ids[0], 160, 90))
    monkeypatch.setattr("gflow_cli.api.native_video_upscale.read_promotion_source", measured)
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    monkeypatch.setattr(module, "new_extension_started", lambda *_: S)
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *_: {
            "media": [
                {
                    "media_id": S.source_media_id,
                    "kind": "video",
                    "width": None if missing_dimensions else 160,
                    "height": None if missing_dimensions else 90,
                }
            ]
        },
    )
    monkeypatch.setattr(
        module, "project_media", lambda *_: [{"media_id": S.source_media_id, "archived": False}]
    )
    monkeypatch.setattr(module, "_read_native", AsyncMock(return_value=[None, None, None, 1]))
    monkeypatch.setattr(
        module, "parse_extension_models", lambda *_, **__: [{"model_key": "explicit-edit-key"}]
    )
    mint = AsyncMock(return_value="test")
    monkeypatch.setattr(module, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    monkeypatch.setattr(module, "rpc_errors", lambda _: [])
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda _: [
            ("jIps6", [None, None, None, [[S.media_ids[0], S.project_id, S.workflow_ids[0]]]])
        ],
    )
    checkpoint = AsyncMock()
    result = await module.edit_native_video(
        client,
        project_id=S.project_id,
        media_id=S.source_media_id,
        prompt="edit",
        model_key="explicit-edit-key",
        end_frame=120,
        on_started=checkpoint,
    )
    assert result.media_ids == S.media_ids
    assert result.end_frame == 120
    checkpoint.assert_awaited_once_with(result)
    page.evaluate.assert_awaited_once()
    assert page.evaluate.call_args.args[1]["rpc"] == "jIps6"
    if missing_dimensions:
        measured.assert_awaited_once_with(page, project_id=S.project_id, media_id=S.source_media_id)
    else:
        measured.assert_not_awaited()
    client._checkin_page.assert_called_once_with(page)


def test_model_catalog_requires_edit_not_extension():
    from gflow_cli.api.native_extension import parse_extension_models

    usage = [None] * 25
    usage[0] = "edit-key"
    usage[4] = [[2, [[None, 10]]]]
    usage[7] = [[[[1, 6, 20]]]]
    payload = [[None, None, None, None, [["Omni", [usage], None, "omni"]]]]
    assert (
        parse_extension_models(payload, tier=2, required_requirements=(1, 6, 20))[0]["model_key"]
        == "edit-key"
    )
    assert parse_extension_models(payload, tier=2) == []
    usage[7] = [[[[1, 14]]]]
    assert parse_extension_models(payload, tier=2, required_requirements=(1, 6, 20)) == []


def test_video_edit_character_and_mixed_positional_chunks():
    from gflow_cli.api.native_extension import new_extension_started
    from gflow_cli.api.native_video_edit import video_edit_args
    from gflow_cli.api.reference_markers import ReferenceSlot
    from tests.api.transports.test_character_details import E, M, P

    started = new_extension_started(P, M, 1)
    row = video_edit_args(
        started,
        prompt="@referenceImage_3 and @referenceImage_1",
        model_key="edit",
        aspect="16:9",
        token="test",
        image_ids=(M,),
        character_ids=(E,),
        reference_slots={
            "referenceImage_1": ReferenceSlot("image", M),
            "referenceImage_3": ReferenceSlot("character", E),
        },
    )[0][0]
    assert row[8] == [[None, M]] and row[9] == [] and row[10] == [[E]]
    assert row[1][2][0] == [[None, [None, None, [E, ""]]], [" and "], [None, [[M, ""]]]]
    assert row[4][4:] == [started.media_seeds[0], started.workflow_seeds[0]]
