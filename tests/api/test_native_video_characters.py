"""Character video capacity comes from actual owned linked references."""

from copy import deepcopy

import pytest

from gflow_cli.api.native_video_characters import character_reference_counts, reference_capacity
from gflow_cli.errors import ConfigurationError
from tests.api.transports.test_character_details import E, P, fixture


def test_two_owned_image_refs_count_two():
    assert character_reference_counts(fixture(), P, (E,)) == {E: (2, 0)}


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_entity",
        "duplicate_workflow",
        "archived",
        "foreign_parent",
        "missing_image",
        "mixed_kind",
        "zero_images",
        "bad_voice",
    ],
)
def test_character_ambiguity_refuses(mutation):
    payload = fixture()
    if mutation == "duplicate_entity":
        payload[5].append(deepcopy(payload[5][0]))
    elif mutation == "duplicate_workflow":
        payload[1].append(deepcopy(payload[1][0]))
    elif mutation == "archived":
        payload[1][0][3][2] = True
    elif mutation == "foreign_parent":
        payload[1][0][5] = P
    elif mutation == "missing_image":
        payload[2].pop(0)
    elif mutation == "mixed_kind":
        payload[2][0].extend([[], None, None, [[1]]])
    elif mutation == "zero_images":
        payload[5][0][3][2][0] = []
    else:
        payload[5][0][3][2][1] = [["unknown"]]
    with pytest.raises(ConfigurationError):
        character_reference_counts(payload, P, (E,))


def test_known_preset_consumes_audio_metadata_slot():
    payload = fixture()
    payload[5][0][3][2][1] = [[None, "charon"]]
    assert character_reference_counts(payload, P, (E,)) == {E: (2, 1)}


def test_actual_character_weights_and_three_pools():
    assert reference_capacity(1, 1, {E: (2, 1)}, (2, 1, 3))
    assert not reference_capacity(2, 1, {E: (2, 1)}, (2, 1, 3))
    assert not reference_capacity(1, 2, {E: (2, 1)}, (2, 1, 3))
    assert not reference_capacity(1, 1, {E: (2, 1)}, (2, 0, 3))
    assert not reference_capacity(1, 1, {E: (2, 1)}, (None, 1, 3))


def test_zero_audio_capacity_ignores_linked_voice_as_frontend_does():
    assert reference_capacity(1, 0, {E: (2, 1)}, (0, 1, 3))
    assert not reference_capacity(1, 1, {E: (2, 1)}, (0, 1, 3))


def test_character_entity_vector_and_structured_marker():
    from gflow_cli.api.native_reference_video import new_reference_started, reference_args

    row = reference_args(
        new_reference_started(P, 1),
        prompt="Use @character_1",
        image_ids=(),
        character_ids=(E,),
        model_key="native",
        aspect="16:9",
        resolution="720p",
        token="test",
    )[0][0]
    assert row[9] == [[E]]
    assert row[0][2][0] == [["Use "], [None, [None, None, [E, ""]]]]
    assert row[1] == [] and row[7] == []


def test_mixed_canonical_slots_preserve_indices_and_entity_arm():
    from gflow_cli.api.native_reference_video import new_reference_started, reference_args
    from gflow_cli.api.reference_markers import ReferenceSlot
    from tests.api.transports.test_character_details import M

    row = reference_args(
        new_reference_started(P, 1),
        prompt="@referenceImage_3 then @referenceImage_1",
        image_ids=(M,),
        character_ids=(E,),
        reference_slots={
            "referenceImage_1": ReferenceSlot("image", M),
            "referenceImage_3": ReferenceSlot("character", E),
        },
        model_key="native",
        aspect="16:9",
        resolution="1080p",
        token="test",
    )[0][0]
    assert row[0][2][0] == [[None, [None, None, [E, ""]]], [" then "], [None, [[M, ""]]]]
    assert row[9] == [[E]] and row[11] == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed", [False, True])
async def test_character_dispatch_and_native_capacity(monkeypatch, mixed):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_reference_video as module
    from tests.api.transports.test_character_details import M

    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=Mock())
    started = module.new_reference_started(P, 1)
    monkeypatch.setattr(module, "new_reference_started", lambda *_: started)
    read = AsyncMock(return_value=fixture())
    monkeypatch.setattr(module, "read_project_payload", read)
    usage = [None] * 25
    usage[0] = "native"
    usage[21] = [0, 1, 3]
    monkeypatch.setattr(
        module,
        "_read_native",
        AsyncMock(
            side_effect=[[[None, None, None, None, [["Omni", [usage]]]]], [None, None, None, 1]]
        ),
    )
    monkeypatch.setattr(
        module,
        "parse_extension_models",
        lambda *_, **__: [
            {
                "model_key": "native",
                "aspect_enums": [2],
                "duration": 8,
                "credits": 10,
                "display_name": "Omni Flash",
            }
        ],
    )
    from gflow_cli.api import recaptcha

    mint = AsyncMock(return_value="test")
    monkeypatch.setattr(recaptcha, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    monkeypatch.setattr(module, "rpc_errors", lambda _: [])
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda _: [
            ("MZZa6b", [None, None, None, [[started.media_ids[0], P, started.workflow_ids[0]]]])
        ],
    )
    kwargs = {"reference_character_ids": (E,), "prompt": "@character_1"}
    if mixed:
        kwargs = {
            "reference_image_ids": (M, E),
            "reference_slot_ids": {"referenceImage_1": M, "referenceImage_3": E},
            "prompt": "@referenceImage_3 then @referenceImage_1",
        }
    checkpoint = AsyncMock()
    result = await module.generate_native_reference_video(
        client, project_id=P, model_key="native", on_started=checkpoint, **kwargs
    )
    assert result == started
    read.assert_awaited_once_with(page, P)
    mint.assert_awaited_once_with("VIDEO_GENERATION")
    checkpoint.assert_awaited_once_with(started)
    page.evaluate.assert_awaited_once()
    row = page.evaluate.call_args.args[1]["args"][0][0]
    assert row[9] == [[E]]
    assert row[1] == ([[None, M]] if mixed else [])
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_sdk_forwards_character_and_canonical_slot_ids(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_reference_video as module
    from gflow_cli.api.client import FlowApiClient

    generate = AsyncMock(return_value="started")
    monkeypatch.setattr(module, "generate_native_reference_video", generate)
    client = object.__new__(FlowApiClient)
    slots = {"character_2": E}
    assert (
        await client.generate_native_reference_video(
            project_id=P,
            prompt="@character_2",
            reference_character_ids=(E,),
            reference_slot_ids=slots,
        )
        == "started"
    )
    assert generate.call_args.kwargs["reference_character_ids"] == (E,)
    assert generate.call_args.kwargs["reference_slot_ids"] == slots


@pytest.mark.asyncio
async def test_private_worker_forwards_canonical_character_slots(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.selfhost import reference_video_worker as module

    api = AsyncMock()
    generate = AsyncMock(return_value=module.new_reference_started(P, 1))
    monkeypatch.setattr(module, "generate_native_reference_video", generate)
    monkeypatch.setattr(module, "wait_native_reference_video", AsyncMock(return_value=()))
    context = AsyncMock()
    context.__aenter__.return_value = api
    monkeypatch.setattr(module, "FlowApiClient", lambda **_: context)
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(profile_subdir=lambda _: tmp_path)
    )
    result = await module.run_reference_video(
        "profile",
        P,
        {
            "prompt": "@character_2",
            "referenceCharacterIds": [E],
            "referenceSlotIds": {"character_2": E},
        },
        tmp_path,
    )
    assert result["results"] == []
    assert generate.call_args.kwargs["reference_character_ids"] == (E,)
    assert generate.call_args.kwargs["reference_slot_ids"] == {"character_2": E}


def test_registered_mcp_character_input_is_available():
    from gflow_cli.mcp import tools

    tool = tools.server._tool_manager.get_tool("gflow_generate_native_reference_video")
    model = tool.fn_metadata.arg_model.model_validate(
        {"project": P, "prompt": "@character_1", "character_ref": [E]}
    )
    assert model.character_ref == [E]


def test_cross_kind_raw_entity_duplicate_refuses():
    payload = fixture()
    other = deepcopy(payload[5][0])
    other[3][0] = 2
    payload[5].insert(0, other)
    with pytest.raises(ConfigurationError):
        character_reference_counts(payload, P, (E,))


@pytest.mark.asyncio
async def test_mixed_slot_namespace_collision_refuses_before_model_or_mint(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_reference_video as module

    payload = fixture()
    payload[2][0][0] = E
    page = SimpleNamespace(evaluate=AsyncMock())
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=Mock())
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload))
    models = AsyncMock()
    monkeypatch.setattr(module, "_read_native", models)
    with pytest.raises(ConfigurationError):
        await module.generate_native_reference_video(
            client,
            project_id=P,
            prompt="@referenceImage_1",
            reference_image_ids=(E,),
            reference_slot_ids={"referenceImage_1": E},
            model_key="native",
        )
    models.assert_not_awaited()
    page.evaluate.assert_not_awaited()
    client._checkin_page.assert_called_once_with(page)
