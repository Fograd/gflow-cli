"""Only measured same-project upload acknowledgements can name a binding."""

import json

import pytest

from gflow_cli.api.transports import migrated_composer as source

MEDIA = "11111111-1111-4111-8111-111111111111"
PROJECT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


def frames(*payloads):
    return json.dumps([["wrb.fr", "maseQ", json.dumps(payload)] for payload in payloads])


def test_measured_flat_upload_ack_correlates_project():
    assert source._uploaded_image_id(frames([MEDIA, PROJECT, OTHER, "CAE"]), PROJECT) == MEDIA


@pytest.mark.parametrize(
    "payload",
    [
        [MEDIA, OTHER, "CAE"],
        [PROJECT, MEDIA, "CAE"],
        [[MEDIA, PROJECT]],
        {"id": MEDIA, "project": PROJECT},
        [None, PROJECT, MEDIA],
        ["noise " + MEDIA, PROJECT],
        [MEDIA],
    ],
)
def test_unrelated_nested_or_reversed_ack_cannot_bind(payload):
    assert source._uploaded_image_id(frames(payload), PROJECT) is None


def test_multiple_upload_frames_are_ambiguous_even_with_equal_ids():
    assert source._uploaded_image_id(frames([MEDIA, PROJECT], [MEDIA, PROJECT]), PROJECT) is None


def current_ack():
    workflow = "44444444-4444-4444-8444-444444444444"
    stamp = [1791038277, 120539000]
    return [
        [
            MEDIA,
            PROJECT,
            workflow,
            None,
            None,
            [stamp, None, None, None, None, None, [None, None, None, None, 1]],
            [None, [None, None, None, None, 0, None, "image/png"], [48, 32]],
        ],
        [workflow, None, None, ["synthetic-owned-tag.png", stamp, None, None, MEDIA], PROJECT],
    ]


def test_current_nested_image_ack_matches_project_media_workflow_and_caption():
    assert (
        source._uploaded_image_id(frames(current_ack()), PROJECT, "synthetic-owned-tag.png")
        == MEDIA
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ((0, 1), OTHER),
        ((0, 2), OTHER),
        ((1, 0), OTHER),
        ((1, 3, 4), OTHER),
        ((1, 4), OTHER),
        ((1, 3, 0), "another-file.png"),
        ((0, 6, 2), [0, 32]),
        ((0, 6, 2), [True, 32]),
        ((0, 6, 2), None),
        ((0, 6, 1, 6), []),
    ],
)
def test_current_nested_ack_rejects_unmatched_identity_or_nonimage(field, value):
    payload = current_ack()
    target = payload
    for index in field[:-1]:
        target = target[index]
    target[field[-1]] = value
    assert source._uploaded_image_id(frames(payload), PROJECT, "synthetic-owned-tag.png") is None
