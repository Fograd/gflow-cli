from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.image import GenerateImageRequest, ImageRef
from gflow_cli.api.reference_markers import ReferenceContractError
from gflow_cli.services.mentions import AssetIndex, resolve_and_apply
from gflow_cli.worker.codec import build_image_request

IMAGE_ID = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
async def test_slot_mode_preserves_unknown_literals_and_never_named_lookup(monkeypatch):
    lookup = AsyncMock(side_effect=AssertionError("named index must not run"))
    monkeypatch.setattr(AssetIndex, "build_for_project", lookup)
    request = GenerateImageRequest(
        prompt="@reference_1 beside @character_1; contact café@example.test",
        refs=(ImageRef(IMAGE_ID),),
        reference_entities=(E,),
        reference_syntax="slots",
    )
    result = await resolve_and_apply(
        Mock(), request, path="image", project_id=IMAGE_ID, tool_specs=()
    )
    assert result.prompt == request.prompt
    assert result.reference_prompt_plan.has_markers
    lookup.assert_not_awaited()


def test_worker_codec_retains_slot_mode_and_resolves_before_browser():
    request = build_image_request(
        {"prompt": "@reference_1", "refs": [IMAGE_ID], "reference_syntax": "slots"}
    )
    assert request.reference_syntax == "slots"
    assert request.reference_prompt_plan.has_markers


def test_invalid_slot_refuses_at_worker_decode():
    with pytest.raises((ValueError, ReferenceContractError)):
        build_image_request(
            {"prompt": "@reference_2", "refs": [IMAGE_ID], "reference_syntax": "slots"}
        )


def test_unknown_syntax_refuses_not_silently_ignored():
    with pytest.raises(ValueError, match="syntax"):
        GenerateImageRequest(prompt="plain", reference_syntax="made-up")


def test_explicit_plan_codec_round_trip_preserves_slot_gaps_and_repeats():
    from gflow_cli.api.reference_markers import (
        ReferenceSlot,
        prepare_image_slot_request,
        reference_plan_record,
    )

    request = prepare_image_slot_request(
        GenerateImageRequest(prompt="@reference_3 then @reference_3", refs=(ImageRef(IMAGE_ID),)),
        {"reference_3": ReferenceSlot("image", IMAGE_ID)},
    )
    restored = build_image_request(
        {
            "prompt": request.prompt,
            "refs": [IMAGE_ID],
            "reference_prompt_plan": reference_plan_record(request.reference_prompt_plan),
        }
    )
    assert restored.reference_prompt_plan == request.reference_prompt_plan


def test_unknown_serialized_plan_is_refused():
    with pytest.raises(ValueError):
        build_image_request(
            {"prompt": "plain", "reference_prompt_plan": {"unknown": "do not ignore"}}
        )
