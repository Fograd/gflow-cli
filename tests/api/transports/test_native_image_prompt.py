from __future__ import annotations

import json
from urllib.parse import urlencode

from gflow_cli.api.transports.native_image_prompt import NativePromptChunk, prompt_submit_problem

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
E = "33333333-3333-4333-8333-333333333333"


def envelope(chunks=None, media=None, entities=None):
    row = [None] * 14
    row[2] = media if media is not None else [[M, None, None, None, 1]]
    row[7] = [None, None, None, None, None, P]
    row[8] = [
        chunks
        if chunks is not None
        else [
            ["Draw "],
            [None, [[M, "Mug"]]],
            [" beside "],
            [None, [None, None, [E, "Hero"]]],
            [" and "],
            [None, [[M, "Mug"]]],
            ["."],
        ]
    ]
    row[10] = entities if entities is not None else [[E]]
    args = [None, [row], 1, [None, None, None, None, None, P]]
    return urlencode({"f.req": json.dumps([[["ogiZ0b", json.dumps(args), None, "generic"]]])})


def expected():
    return (
        NativePromptChunk("text", "Draw "),
        NativePromptChunk("image", M, "Mug"),
        NativePromptChunk("text", " beside "),
        NativePromptChunk("character", E, "Hero"),
        NativePromptChunk("text", " and "),
        NativePromptChunk("image", M, "Mug"),
        NativePromptChunk("text", "."),
    )


def test_actual_ordered_repeats_with_dedup_vectors_pass():
    assert prompt_submit_problem(envelope(), P, expected()) is None


def test_literal_text_substitution_does_not_ground():
    assert (
        prompt_submit_problem(envelope(chunks=[["Draw Mug beside Hero and Mug."]]), P, expected())
        is not None
    )


def test_wrong_order_or_dropped_repeat_refuses():
    assert (
        prompt_submit_problem(
            envelope(
                chunks=[
                    ["Draw "],
                    [None, [[M, "Mug"]]],
                    [" beside "],
                    [None, [None, None, [E, "Hero"]]],
                    [" and ."],
                ]
            ),
            P,
            expected(),
        )
        is not None
    )


def test_extra_or_missing_attachment_refuses():
    assert prompt_submit_problem(envelope(media=[]), P, expected()) is not None
    assert prompt_submit_problem(envelope(entities=[[E], ["other"]]), P, expected()) is not None


def test_unknown_chunk_shape_refuses():
    assert prompt_submit_problem(envelope(chunks=[{"media": M}]), P, expected()) is not None


async def test_materialization_preserves_literal_spans_and_repeated_positions():
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
    from gflow_cli.api.transports.native_image_prompt import (
        NativeImageBinding,
        materialize_reference_prompt,
    )

    plan = resolve_reference_markers(
        "Draw @reference_1 beside @character_1 and @reference_1.",
        surface="image",
        slots={
            "reference_1": ReferenceSlot("image", M),
            "character_1": ReferenceSlot("character", E, 1),
        },
    )
    composer = MagicMock()
    composer.clear_composer = AsyncMock()
    composer._mention_by_token = AsyncMock()
    composer._mention_by_name = AsyncMock()
    composer.read_chips = AsyncMock(
        side_effect=[
            [{"reference_type": "media"}],
            [{"reference_type": "media"}, {"reference_type": "entity", "entity_id": E}],
            [
                {"reference_type": "media"},
                {"reference_type": "entity", "entity_id": E},
                {"reference_type": "media"},
            ],
        ]
    )
    page = MagicMock()
    page.keyboard.insert_text = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.locator.return_value.first.evaluate = AsyncMock(return_value=True)
    result = await materialize_reference_prompt(
        page, composer, plan, {M: NativeImageBinding(M, "Mug", "token")}, {E: "Hero"}
    )
    assert result == expected()
    assert page.keyboard.press.await_count == 3
    page.keyboard.press.assert_awaited_with("Backspace")
    assert [call.args[0] for call in page.keyboard.insert_text.await_args_list] == [
        "Draw ",
        " beside ",
        " and ",
        ".",
    ]
    assert composer._mention_by_token.await_count == 2
    composer._mention_by_name.assert_awaited_once_with(
        page, "Hero", expect_chips=2, at_end=True, trailing_space=False
    )


async def test_full_route_guard_aborts_literal_rewrite_before_submission():
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.transports.migrated_composer import _guard_image_submit

    route = MagicMock(abort=AsyncMock(), continue_=AsyncMock())
    request = MagicMock(post_data=envelope(chunks=[["Draw Mug beside Hero and Mug."]]))
    problem = await _guard_image_submit(
        route, request, (), None, project_id=P, expected_prompt=expected()
    )
    assert problem is not None
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()


async def test_marker_request_uses_actual_upload_bindings_and_wire_plan(monkeypatch):
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
    from gflow_cli.api.transports import migrated_composer
    from gflow_cli.api.transports.native_image_prompt import NativeImageBinding

    logical = "55555555-5555-4555-8555-555555555555"
    plan = resolve_reference_markers(
        "Draw @reference_1.",
        surface="image",
        slots={"reference_1": ReferenceSlot("image", logical)},
    )
    composer = MagicMock()
    composer.ensure_editor = AsyncMock()
    composer.apply_image_settings = AsyncMock()
    composer.upload_reference_bindings = AsyncMock(
        return_value=(NativeImageBinding(M, "Uploaded"),)
    )
    composer.submit_images_and_observe = AsyncMock(return_value=[])
    chunks = (
        NativePromptChunk("text", "Draw "),
        NativePromptChunk("image", M, "Uploaded"),
        NativePromptChunk("text", "."),
    )
    materialize = AsyncMock(return_value=chunks)
    monkeypatch.setattr(migrated_composer, "MigratedComposer", MagicMock(return_value=composer))
    monkeypatch.setattr(migrated_composer, "materialize_reference_prompt", materialize)
    request = GenerateImageRequest(
        prompt="Draw @reference_1.", ref_paths=(Path("ref.png"),), reference_prompt_plan=plan
    )
    page = MagicMock(url="https://flow.google.com/project/" + P)
    await migrated_composer.run_images(page, request, project_id=P)
    materialize.assert_awaited_once_with(
        page, composer, plan, {logical: NativeImageBinding(M, "Uploaded")}, {}
    )
    composer.submit_images_and_observe.assert_awaited_once_with(
        page, request, project_id=P, reference_ids=(M,), expected_prompt=chunks
    )


async def test_picker_space_cleanup_refuses_unknown_caret_without_deleting():
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from gflow_cli.api.transports.native_image_prompt import remove_picker_space

    page = MagicMock()
    page.locator.return_value.first.evaluate = AsyncMock(return_value=False)
    page.keyboard.press = AsyncMock()
    with pytest.raises(ValueError, match="picker separator"):
        await remove_picker_space(page)
    page.keyboard.press.assert_not_awaited()


async def test_mixed_native_local_bindings_preserve_plan_order_and_actual_upload_id(monkeypatch):
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request
    from gflow_cli.api.transports import migrated_composer
    from gflow_cli.api.transports.native_image_prompt import NativeImageBinding

    first = "44444444-4444-4444-8444-444444444444"
    alias = "55555555-5555-4555-8555-555555555555"
    last = "66666666-6666-4666-8666-666666666666"
    prompt = "Draw @reference_3 beside @reference_1 and @reference_2 plus @reference_1."
    request = prepare_image_slot_request(
        GenerateImageRequest(
            prompt=prompt,
            refs=(
                ImageRef(first, display_name="First", in_project=True),
                ImageRef(last, display_name="Last", in_project=True),
            ),
            ref_paths=(Path("managed.png"),),
            local_ref_ids=(alias,),
        ),
        {
            "reference_1": ReferenceSlot("image", first),
            "reference_2": ReferenceSlot("image", alias),
            "reference_3": ReferenceSlot("image", last),
        },
    )
    composer = MagicMock()
    composer.ensure_editor = AsyncMock()
    composer.apply_image_settings = AsyncMock()
    composer.reference_existing = AsyncMock(return_value=(first, last))
    composer.await_existing_references = AsyncMock(
        side_effect=[
            {first: "oldFirstToken", last: "oldLastToken"},
            {first: "firstToken", last: "lastToken"},
        ]
    )
    composer.upload_reference_bindings = AsyncMock(
        return_value=(NativeImageBinding(M, "Uploaded"),)
    )
    composer.submit_images_and_observe = AsyncMock(return_value=[])
    chunks = (
        NativePromptChunk("text", "Draw "),
        NativePromptChunk("image", last, "Last"),
        NativePromptChunk("text", " beside "),
        NativePromptChunk("image", first, "First"),
        NativePromptChunk("text", " and "),
        NativePromptChunk("image", M, "Uploaded"),
        NativePromptChunk("text", " plus "),
        NativePromptChunk("image", first, "First"),
        NativePromptChunk("text", "."),
    )
    materialize = AsyncMock(return_value=chunks)
    monkeypatch.setattr(migrated_composer, "MigratedComposer", MagicMock(return_value=composer))
    monkeypatch.setattr(migrated_composer, "materialize_reference_prompt", materialize)
    page = MagicMock(url="https://flow.google.com/project/" + P)
    await migrated_composer.run_images(page, request, project_id=P)
    materialize.assert_awaited_once_with(
        page,
        composer,
        request.reference_prompt_plan,
        {
            first: NativeImageBinding(first, "First", "firstToken"),
            alias: NativeImageBinding(M, "Uploaded"),
            last: NativeImageBinding(last, "Last", "lastToken"),
        },
        {},
    )
    composer.submit_images_and_observe.assert_awaited_once_with(
        page,
        request,
        project_id=P,
        reference_ids=(first, M, last),
        expected_prompt=chunks,
    )
    composer.upload_reference_bindings.assert_awaited_once_with(page, P, (Path("managed.png"),))


async def test_conflicting_local_alias_refuses_before_composer_or_upload(monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock

    import pytest

    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
    from gflow_cli.api.transports import migrated_composer
    from gflow_cli.errors import ConfigurationError

    alias = "55555555-5555-4555-8555-555555555555"
    prompt = "Use @reference_1 with @reference_2."
    plan = resolve_reference_markers(
        prompt,
        surface="image",
        slots={
            "reference_1": ReferenceSlot("image", M),
            "reference_2": ReferenceSlot("image", alias),
        },
    )
    request = GenerateImageRequest(
        prompt=prompt,
        refs=(ImageRef(M, display_name="Owned", in_project=True),),
        ref_paths=(Path("managed.png"),),
        local_ref_ids=(M,),
        reference_prompt_plan=plan,
    )
    constructor = MagicMock()
    monkeypatch.setattr(migrated_composer, "MigratedComposer", constructor)
    with pytest.raises(ConfigurationError):
        await migrated_composer.run_images(MagicMock(), request, project_id=P)
    constructor.assert_not_called()


async def test_uploaded_handles_survive_prompt_binding_failure(monkeypatch):
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.reference_markers import prepare_explicit_image_inputs
    from gflow_cli.api.transports import migrated_composer
    from gflow_cli.api.transports.native_image_prompt import NativeImageBinding
    from gflow_cli.errors import NativeMediaMutationUnknownError, ReferenceNotFoundError

    path = Path("managed.png")
    request = prepare_explicit_image_inputs(
        GenerateImageRequest(prompt="Use @reference_1.", ref_paths=(path,)), (path,)
    )
    composer = MagicMock()
    composer.ensure_editor = AsyncMock()
    composer.apply_image_settings = AsyncMock()
    composer.upload_reference_bindings = AsyncMock(return_value=(NativeImageBinding(M, "Upload"),))
    composer.submit_images_and_observe = AsyncMock()
    monkeypatch.setattr(migrated_composer, "MigratedComposer", MagicMock(return_value=composer))
    monkeypatch.setattr(
        migrated_composer,
        "materialize_reference_prompt",
        AsyncMock(side_effect=ReferenceNotFoundError(detail="picker unavailable")),
    )
    with pytest.raises(NativeMediaMutationUnknownError) as err:
        await migrated_composer.run_images(
            MagicMock(url="https://flow.google.com/project/" + P), request, project_id=P
        )
    assert err.value.known_media_ids == (M,)
    composer.submit_images_and_observe.assert_not_awaited()
