"""R2V requires the same fresh active audio proof as editing, with five slots."""

from copy import deepcopy
from uuid import UUID

import pytest

from gflow_cli.api.native_reference_video import validate_reference_assets
from gflow_cli.errors import ConfigurationError
from tests.api.test_native_edit_audio import OTHER, A, P, fixture


@pytest.mark.parametrize("saved", [False, True])
def test_reference_audio_accepts_saved_and_unsaved_active_native_audio(saved):
    validate_reference_assets(fixture(saved), P, (), (A,))


@pytest.mark.parametrize(
    "case",
    [
        "archived",
        "missing_workflow",
        "foreign_workflow",
        "duplicate_workflow",
        "empty_audio",
        "empty_sample",
        "malformed_video",
    ],
)
def test_reference_audio_requires_exclusive_active_owned_workflow(case):
    payload = fixture()
    if case == "archived":
        payload[1][0][3][2] = 1
    elif case == "missing_workflow":
        payload[1] = []
    elif case == "foreign_workflow":
        payload[1][0][4] = OTHER
    elif case == "duplicate_workflow":
        payload[1].append(deepcopy(payload[1][0]))
    elif case == "empty_audio":
        payload[2][0][10] = []
    elif case == "empty_sample":
        payload[2][0][10] = [[]]
    elif case == "malformed_video":
        payload[2][0][7] = "invalid"
    with pytest.raises(ConfigurationError):
        validate_reference_assets(payload, P, (), (A,))


def test_reference_audio_retains_five_audio_outer_limit():
    payload = fixture()
    ids = [A]
    for n in range(4):
        media, workflow = str(UUID(int=n + 10)), str(UUID(int=n + 20))
        row = deepcopy(payload[2][0])
        row[0], row[2] = media, workflow
        parent = deepcopy(payload[1][0])
        parent[0], parent[3][4] = workflow, media
        payload[1].append(parent)
        payload[2].append(row)
        ids.append(media)
    validate_reference_assets(payload, P, (), tuple(ids))


def model_payload():
    usage = [None] * 25
    usage[0] = "native"
    usage[4] = [[1, [[None, 1]]]]
    usage[7] = [[[[1, 6, 18, 19]]]]
    usage[12] = [[2]]
    usage[21] = [5, 2, 7]
    return [[None, None, None, None, [["Omni Flash", [usage]]]]]


def test_model_catalog_exposes_the_fresh_character_pool():
    from gflow_cli.api.native_extension import parse_extension_models

    row = parse_extension_models(model_payload(), tier=1, required_requirements=(1, 6))[0]
    assert row["max_characters"] == 2
    assert row["max_audio"] == 5
    assert row["max_images"] == 7


@pytest.mark.asyncio
async def test_reference_model_duplicate_capacity_refuses_before_mint(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_reference_video as module
    from gflow_cli.api import recaptcha

    page = SimpleNamespace(evaluate=AsyncMock())
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=Mock())
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=fixture()))
    models = model_payload()
    models[0][4][0][1].append(deepcopy(models[0][4][0][1][0]))
    monkeypatch.setattr(
        module, "_read_native", AsyncMock(side_effect=[models, [None, None, None, 1]])
    )
    mint = AsyncMock(return_value="test")
    monkeypatch.setattr(recaptcha, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    checkpoint = AsyncMock()
    with pytest.raises(ConfigurationError):
        await module.generate_native_reference_video(
            client,
            project_id=P,
            prompt="@referenceAudio_1",
            reference_audio_ids=(A,),
            model_key="native",
            on_started=checkpoint,
        )
    mint.assert_not_awaited()
    checkpoint.assert_not_awaited()
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_unrelated_duplicate_models_do_not_block_selected_unique_model(monkeypatch, explicit):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_reference_video as module
    from gflow_cli.api import recaptcha

    class BoundaryError(Exception):
        pass

    page = SimpleNamespace(evaluate=AsyncMock())
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=Mock())
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=fixture()))
    models = model_payload()
    other = deepcopy(models[0][4][0][1][0])
    other[0] = "other"
    models[0][4].append(["Veo", [other, deepcopy(other)]])
    monkeypatch.setattr(
        module, "_read_native", AsyncMock(side_effect=[models, [None, None, None, 1]])
    )
    mint = AsyncMock(side_effect=BoundaryError)
    monkeypatch.setattr(recaptcha, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    with pytest.raises(BoundaryError):
        await module.generate_native_reference_video(
            client,
            project_id=P,
            prompt="@referenceAudio_1",
            reference_audio_ids=(A,),
            model_key="native" if explicit else None,
        )
    mint.assert_awaited_once_with("VIDEO_GENERATION")
    page.evaluate.assert_not_awaited()
