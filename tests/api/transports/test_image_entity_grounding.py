from __future__ import annotations

import json
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.image_entity_grounding import entity_submit_problem

PROJECT = "33333333-3333-4333-8333-333333333333"
ENTITY = "44444444-4444-4444-8444-444444444444"


def envelope(*, chunk_id: str = ENTITY, vector_id: str = ENTITY, project: str = PROJECT) -> str:
    row = [None] * 14
    row[7] = [None] * 6
    row[7][5] = project
    row[8] = [[[None, [None, None, [chunk_id, "Hero"]]], ["a ceramic mug"]]]
    row[10] = [[vector_id]]
    args = [None, [row], 1, [None, None, None, None, None, project]]
    return urlencode({"f.req": json.dumps([[["ogiZ0b", json.dumps(args), None, "generic"]]])})


def test_measured_entity_chunks_and_vector_agree() -> None:
    assert entity_submit_problem(envelope(), PROJECT, (ENTITY,), ("Hero",)) is None


@pytest.mark.parametrize(
    "body",
    [
        envelope(chunk_id="other"),
        envelope(vector_id="other"),
        envelope(project="other"),
        "ogiZ0b " + ENTITY,
        "",
    ],
)
def test_id_substrings_do_not_prove_entity_binding(body: str) -> None:
    assert entity_submit_problem(body, PROJECT, (ENTITY,), ("Hero",)) is not None


def test_wrong_name_and_missing_inputs_are_not_accepted() -> None:
    assert entity_submit_problem(envelope(), PROJECT, (ENTITY,), ("Other",)) is not None
    assert entity_submit_problem(envelope(), PROJECT, (ENTITY,), ()) is not None


async def test_route_guard_aborts_wrong_entity_before_google_acts() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.transports.migrated_composer import _guard_image_submit

    route = MagicMock(abort=AsyncMock(), continue_=AsyncMock())
    request = MagicMock(post_data=envelope(chunk_id="wrong"))
    problem = await _guard_image_submit(
        route, request, (), None, entity_ids=(ENTITY,), entity_names=("Hero",), project_id=PROJECT
    )
    assert problem is not None
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()


async def test_route_guard_accepts_correlated_measured_entity() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.transports.migrated_composer import _guard_image_submit

    route = MagicMock(abort=AsyncMock(), continue_=AsyncMock())
    request = MagicMock(post_data=envelope())
    assert (
        await _guard_image_submit(
            route,
            request,
            (),
            None,
            entity_ids=(ENTITY,),
            entity_names=("Hero",),
            project_id=PROJECT,
        )
        is None
    )
    route.abort.assert_not_awaited()
    route.continue_.assert_awaited_once()


async def test_image_entities_preserve_media_and_append_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.transports import migrated_composer

    composer = MagicMock()
    composer.ensure_editor = AsyncMock()
    composer.apply_image_settings = AsyncMock()
    composer.attach_references = AsyncMock(return_value=("media",))
    composer.read_chips = AsyncMock(return_value=[{"reference_type": "media"}])
    composer.attach_character_entities = AsyncMock()
    composer.send_prompt = AsyncMock()
    composer.submit_images_and_observe = AsyncMock(return_value=[])
    monkeypatch.setattr(migrated_composer, "MigratedComposer", MagicMock(return_value=composer))
    page = MagicMock(url=f"https://flow.google.com/project/{PROJECT}")
    request = GenerateImageRequest(
        prompt="the mug",
        ref_paths=(Path("ref.png"),),
        reference_entities=(ENTITY,),
        reference_entity_names=("Hero",),
    )
    await migrated_composer.run_images(page, request, project_id=PROJECT)
    composer.attach_character_entities.assert_awaited_once_with(
        page, entity_ids=(ENTITY,), names=("Hero",), clear=False
    )
    composer.send_prompt.assert_awaited_once_with(page, "the mug", append=True)


def test_unnamed_entities_refuse_before_browser() -> None:
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.transports.migrated_composer import _unported_image_form

    request = GenerateImageRequest(prompt="the mug", reference_entities=(ENTITY,))
    assert "aligned picker names" in (_unported_image_form(request) or "")


def test_every_output_row_and_entity_vector_is_correlated() -> None:
    fields = parse_qs(envelope())
    frames = json.loads(fields["f.req"][0])
    args = json.loads(frames[0][0][1])
    duplicate = json.loads(json.dumps(args[1][0]))
    duplicate[7][5] = "another-project"
    args[1].append(duplicate)
    frames[0][0][1] = json.dumps(args)
    body = urlencode({"f.req": json.dumps(frames)})
    assert entity_submit_problem(body, PROJECT, (ENTITY,), ("Hero",)) is not None


async def test_dispatch_is_marked_before_continue_can_lose_acknowledgement() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.transports.migrated_composer import _guard_image_submit

    state = {"submitted": False}

    def mark() -> None:
        state["submitted"] = True

    async def dispatch() -> None:
        assert state["submitted"]
        raise TimeoutError("Lost route acknowledgement")

    route = MagicMock(abort=AsyncMock(), continue_=AsyncMock(side_effect=dispatch))
    request = MagicMock(post_data=envelope())
    with pytest.raises(TimeoutError):
        await _guard_image_submit(
            route,
            request,
            (),
            None,
            entity_ids=(ENTITY,),
            entity_names=("Hero",),
            project_id=PROJECT,
            on_submit=mark,
        )
    assert state["submitted"]
    route.abort.assert_not_awaited()
