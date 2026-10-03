"""Ordered native/local canonical inputs must survive the shared queue codec."""

from pathlib import Path

import pytest

from gflow_cli.api.reference_markers import (
    ReferenceMarker,
    ReferenceSlot,
    reference_plan_record,
    resolve_reference_markers,
)
from gflow_cli.errors import QueueSchemaError
from gflow_cli.worker.codec import decode_payload, encode_payload

NATIVE_FIRST = "11111111-1111-4111-8111-111111111111"
LOCAL_ALIAS = "22222222-2222-4222-8222-222222222222"
NATIVE_LAST = "33333333-3333-4333-8333-333333333333"


def mixed_payload():
    prompt = "Put @reference_3 beside @reference_1 and @reference_2 then @reference_1."
    plan = resolve_reference_markers(
        prompt,
        surface="image",
        slots={
            "reference_1": ReferenceSlot("image", NATIVE_FIRST),
            "reference_2": ReferenceSlot("image", LOCAL_ALIAS),
            "reference_3": ReferenceSlot("image", NATIVE_LAST),
        },
    )
    return {
        "prompt": prompt,
        "refs": [NATIVE_FIRST, NATIVE_LAST],
        "ref_paths": ["managed.png"],
        "local_ref_ids": [LOCAL_ALIAS],
        "reference_syntax": "slots",
        "reference_prompt_plan": reference_plan_record(plan),
    }


def test_interleaved_image_sources_round_trip_without_reordering_slots():
    payload = mixed_payload()
    decoded = decode_payload("i2i", payload)
    request = decoded.request
    assert request.local_ref_ids == (LOCAL_ALIAS,)
    assert request.ref_paths == (Path("managed.png"),)
    assert tuple(ref.name for ref in request.refs) == (NATIVE_FIRST, NATIVE_LAST)
    assert request.reference_prompt_plan.image_ids == (
        NATIVE_FIRST,
        LOCAL_ALIAS,
        NATIVE_LAST,
    )
    assert (
        sum(isinstance(span, ReferenceMarker) for span in request.reference_prompt_plan.spans) == 4
    )
    assert encode_payload("i2i", decoded)["local_ref_ids"] == [LOCAL_ALIAS]


@pytest.mark.parametrize("aliases", [[], [NATIVE_FIRST], [LOCAL_ALIAS, NATIVE_LAST], [""]])
def test_incomplete_or_overlapping_local_aliases_refuse_before_execution(aliases):
    payload = mixed_payload()
    payload["local_ref_ids"] = aliases
    with pytest.raises(QueueSchemaError):
        decode_payload("i2i", payload)


def test_native_subset_cannot_be_reordered():
    payload = mixed_payload()
    payload["refs"] = [NATIVE_LAST, NATIVE_FIRST]
    with pytest.raises(QueueSchemaError):
        decode_payload("i2i", payload)


def test_local_aliases_must_retain_filtered_plan_order():
    payload = mixed_payload()
    payload["refs"] = [NATIVE_FIRST]
    payload["ref_paths"] = ["second.png", "third.png"]
    payload["local_ref_ids"] = [NATIVE_LAST, LOCAL_ALIAS]
    with pytest.raises(QueueSchemaError):
        decode_payload("i2i", payload)


@pytest.mark.parametrize("aliases", [[LOCAL_ALIAS, LOCAL_ALIAS], [LOCAL_ALIAS, "unknown"]])
def test_duplicate_or_unmatched_local_aliases_are_not_valid_bindings(aliases):
    payload = mixed_payload()
    payload["refs"] = [NATIVE_FIRST]
    payload["ref_paths"] = ["second.png", "third.png"]
    payload["local_ref_ids"] = aliases
    with pytest.raises(QueueSchemaError):
        decode_payload("i2i", payload)


def test_explicit_cli_mcp_input_order_builds_interleaved_slots():
    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import prepare_explicit_image_inputs

    ordered = (ImageRef(NATIVE_FIRST), Path("managed.png"), ImageRef(NATIVE_LAST))
    request = GenerateImageRequest(
        prompt="Use @reference_3 with @reference_1 and @reference_2.",
        refs=(ordered[0], ordered[2]),
        ref_paths=(ordered[1],),
        reference_syntax="slots",
    )
    prepared = prepare_explicit_image_inputs(request, ordered)
    assert prepared.local_ref_ids == ("local-reference-2",)
    assert prepared.reference_prompt_plan.image_ids == (
        NATIVE_FIRST,
        "local-reference-2",
        NATIVE_LAST,
    )


def test_explicit_input_order_cannot_remap_an_unrelated_local_path():
    from gflow_cli.api.image import GenerateImageRequest, ImageRef
    from gflow_cli.api.reference_markers import (
        ReferenceContractError,
        prepare_explicit_image_inputs,
    )

    request = GenerateImageRequest(
        prompt="Use @reference_1 and @reference_2.",
        refs=(ImageRef(NATIVE_FIRST),),
        ref_paths=(Path("actual.png"),),
    )
    with pytest.raises(ReferenceContractError):
        prepare_explicit_image_inputs(
            request,
            (ImageRef(NATIVE_FIRST), Path("other.png")),
        )
