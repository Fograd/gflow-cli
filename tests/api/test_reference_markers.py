from __future__ import annotations

import pytest

from gflow_cli.api.reference_markers import (
    ReferenceContractError,
    ReferenceMarker,
    ReferenceSlot,
    TextSpan,
    resolve_reference_markers,
    validate_reference_budget,
)

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def test_unknown_literals_and_no_markers_preserve_prompt_exactly():
    prompt = "Contact user@gmail.com or @anyword_1; @referenceImage_1 is not an image slot."
    plan = resolve_reference_markers(prompt, surface="image", slots={})
    assert plan.spans == (TextSpan(0, len(prompt), prompt),)
    assert not plan.has_markers


def test_mixed_case_repeated_spans_all_slots_and_uuid_dedup():
    prompt = "🙂 @REFERENCE_1, then @reference_2 and @reference_1."
    plan = resolve_reference_markers(
        prompt,
        surface="image",
        slots={
            "reference_1": ReferenceSlot("image", A),
            "reference_2": ReferenceSlot("image", A.upper()),
            "reference_3": ReferenceSlot("image", B),
        },
    )
    markers = [span for span in plan.spans if isinstance(span, ReferenceMarker)]
    assert [span.slot for span in markers] == ["reference_1", "reference_2", "reference_1"]
    assert all(span.identifier == A for span in markers)
    assert plan.image_ids == (A, B)
    assert "".join(prompt[span.start : span.end] for span in plan.spans) == prompt


def test_supplied_unmentioned_character_and_audio_are_attached():
    plan = resolve_reference_markers(
        "plain text",
        surface="video",
        slots={
            "referenceImage_1": ReferenceSlot("image", A),
            "character_1": ReferenceSlot("character", B, image_count=2),
            "referenceAudio_1": ReferenceSlot("audio", "Charon"),
        },
    )
    assert plan.image_ids == (A,)
    assert plan.character_ids == (B,)
    assert plan.audio_ids == ("Charon",)


@pytest.mark.parametrize("token", ["@reference_0", "@reference_11", "@reference_01"])
def test_reserved_invalid_index_refused(token):
    with pytest.raises(ReferenceContractError):
        resolve_reference_markers(token, surface="image", slots={})


def test_missing_slot_problem_excludes_identifiers():
    with pytest.raises(ReferenceContractError, match="reference_2.*not provided"):
        resolve_reference_markers(
            "@reference_2", surface="image", slots={"reference_1": ReferenceSlot("image", A)}
        )


def test_video_inline_video_marker_refused_even_with_body_slot():
    with pytest.raises(ReferenceContractError, match="not supported inline"):
        resolve_reference_markers(
            "@referenceVideo_1",
            surface="video",
            slots={"referenceVideo_1": ReferenceSlot("video", A)},
        )


def test_prefix_suffix_words_are_literal_conservative_token_policy():
    prompt = "word@reference_1 @reference_1suffix @reference_1_more @reference_１２"
    plan = resolve_reference_markers(prompt, surface="image", slots={})
    assert plan.spans == (TextSpan(0, len(prompt), prompt),)


def test_image_budget_counts_distinct_character_images():
    plan = resolve_reference_markers(
        "@character_1",
        surface="image",
        slots={
            "reference_1": ReferenceSlot("image", A),
            "character_1": ReferenceSlot("character", B, image_count=2),
        },
    )
    assert validate_reference_budget(plan, surface="image", model="nano-banana-2") == 3
    with pytest.raises(ReferenceContractError, match="budget"):
        validate_reference_budget(plan, surface="image", model="nano-banana-2", native_image_cap=2)


@pytest.mark.parametrize("count", [None, 0, True, -1])
def test_unknown_or_invalid_character_count_refused(count):
    plan = resolve_reference_markers(
        "", surface="image", slots={"character_1": ReferenceSlot("character", B, image_count=count)}
    )
    with pytest.raises(ReferenceContractError, match="verified image count"):
        validate_reference_budget(plan, surface="image", model="nano-banana-pro")


def test_veo_weighted_cap_and_voice_prerequisite():
    plan = resolve_reference_markers(
        "",
        surface="video",
        slots={
            "referenceImage_1": ReferenceSlot("image", A),
            "character_1": ReferenceSlot("character", B, image_count=2),
            "referenceAudio_1": ReferenceSlot("audio", "Charon"),
        },
    )
    assert validate_reference_budget(plan, surface="video", model="veo-3.1-fast") == 3
    with pytest.raises(ReferenceContractError, match="8"):
        validate_reference_budget(plan, surface="video", model="veo-3.1-fast", duration=6)
    with pytest.raises(ReferenceContractError, match="quality"):
        validate_reference_budget(plan, surface="video", model="veo-3.1-quality")
    audio = resolve_reference_markers(
        "", surface="video", slots={"referenceAudio_1": ReferenceSlot("audio", "Charon")}
    )
    with pytest.raises(ReferenceContractError, match="requires"):
        validate_reference_budget(audio, surface="video", model="omni-flash")


def test_omni_v2v_has_separate_limits_and_no_duration():
    slots = {f"referenceImage_{i}": ReferenceSlot("image", f"media-{i}") for i in range(1, 7)}
    slots["referenceVideo_1"] = ReferenceSlot("video", C)
    plan = resolve_reference_markers("", surface="video", slots=slots)
    with pytest.raises(ReferenceContractError, match="budget"):
        validate_reference_budget(plan, surface="video", model="omni-flash")
    slots.pop("referenceImage_6")
    plan = resolve_reference_markers("", surface="video", slots=slots)
    assert validate_reference_budget(plan, surface="video", model="omni-flash") == 5
    with pytest.raises(ReferenceContractError, match="duration"):
        validate_reference_budget(plan, surface="video", model="omni-flash", duration=8)


def test_frames_and_ingredients_are_mutually_exclusive():
    plan = resolve_reference_markers(
        "", surface="video", slots={"referenceImage_1": ReferenceSlot("image", A)}
    )
    with pytest.raises(ReferenceContractError, match="frames"):
        validate_reference_budget(plan, surface="video", model="omni-flash", start_image=True)
    empty = resolve_reference_markers("", surface="video", slots={})
    with pytest.raises(ReferenceContractError, match="requires start"):
        validate_reference_budget(empty, surface="video", model="omni-flash", end_image=True)


def test_budget_refuses_surface_mismatch():
    plan = resolve_reference_markers("", surface="image", slots={})
    with pytest.raises(ReferenceContractError, match="surface"):
        validate_reference_budget(plan, surface="video", model="omni-flash")


def test_budget_refuses_boolean_duration():
    plan = resolve_reference_markers("", surface="video", slots={})
    with pytest.raises(ReferenceContractError, match="duration"):
        validate_reference_budget(plan, surface="video", model="omni-flash", duration=True)


def test_slot_request_keeps_prompt_and_reconciles_native_attachments():
    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import prepare_image_slot_request

    image = "11111111-1111-4111-8111-111111111111"
    character = "22222222-2222-4222-8222-222222222222"
    request = GenerateImageRequest(
        prompt="Use @reference_1 with @character_1", refs=(ImageRef(image),)
    )
    prepared = prepare_image_slot_request(
        request,
        {
            "reference_1": ReferenceSlot("image", image),
            "character_1": ReferenceSlot("character", character),
        },
    )
    assert prepared.prompt == request.prompt
    assert prepared.reference_entities == (character,)
    assert prepared.reference_prompt_plan.has_markers


def test_slot_request_rejects_unrepresented_image_before_transport():
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.reference_markers import prepare_image_slot_request

    request = GenerateImageRequest(prompt="@reference_1")
    with pytest.raises(ReferenceContractError, match="attachments"):
        prepare_image_slot_request(
            request, {"reference_1": ReferenceSlot("image", "logical-image")}
        )


@pytest.mark.parametrize(
    "literal", ["café@reference_1.org", "中@character_1.test", "@reference_1３"]
)
def test_unicode_embedded_tokens_remain_literal(literal):
    plan = resolve_reference_markers(literal, surface="image", slots={})
    assert not plan.has_markers
    assert plan.spans[0].text == literal
