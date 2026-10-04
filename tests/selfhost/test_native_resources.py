import pytest

from gflow_cli.api.transports.migrated_resources import project_media, trash_payload

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def test_timeline_identity_is_media_not_workflow():
    rows = project_media(
        [None, [[W, None, None, ["upload", [1], None, None, M], P]], [[M, P, W]]], P
    )
    assert rows[0]["media_id"] == M
    assert rows[0]["workflow_id"] == W
    assert trash_payload([M], rows, P) == [
        [[W, None, None, [None, None, 1], P]],
        [["metadata.archived"]],
    ]


def test_entire_batch_validation_precedes_mutation():
    rows = [{"media_id": M, "workflow_id": W, "project_id": P}]
    with pytest.raises(ValueError):
        trash_payload([M, W], rows, P)


@pytest.mark.parametrize("ids", [[], [M, M], ["wrong"], [M] * 101])
def test_invalid_trash(ids):
    with pytest.raises(ValueError):
        trash_payload(ids, [], P)


def test_cross_project_timeline_refused():
    with pytest.raises(ValueError):
        project_media([None, [[W, None, None, ["x", None, None, None, M], M]], []], P)


def test_trash_refuses_unrequested_sibling_media():
    rows = [
        {
            "media_id": M,
            "workflow_id": W,
            "project_id": P,
            "batch_media_ids": [M, W],
            "archived": False,
        }
    ]
    with pytest.raises(ValueError, match="select every media"):
        trash_payload([M], rows, P)


def test_trash_refuses_unknown_batch_membership():
    rows = [{"media_id": M, "workflow_id": W, "project_id": P, "batch_media_ids": []}]
    with pytest.raises(ValueError, match="membership is unavailable"):
        trash_payload([M], rows, P)


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("uploaded", [True, False])
def test_library_keeps_typed_metadata_and_timeline_fields(kind, uploaded):
    from gflow_cli.selfhost.native_worker import _media_library

    arm = [None, None, [48, 32]] if kind == "image" else [None, [48, 32], None, None, None]
    arm[1 if kind == "image" and uploaded else 4 if uploaded else 0] = ["fixture"]
    row = [M, P, W, None, None, [["1700000000"]], None, None]
    row[6 if kind == "image" else 7] = arm
    payload = [None, [[W, None, None, ["original", [1], None, None, M], P]], [row]]
    result = _media_library(payload, P)
    assert len(result) == 1
    assert result[0]["kind"] == kind and result[0]["likely_upload"] is uploaded
    assert (result[0]["width"], result[0]["height"]) == (48, 32)
    assert result[0]["archived"] is False and result[0]["caption"] == "original"
    assert result[0]["created_time"] == "2023-11-14T22:13:20Z"
    assert "fixture" not in str(result)


def test_library_preserves_attached_origin_and_unknown_timeline():
    from gflow_cli.selfhost.native_worker import _media_library

    foreign = "44444444-4444-4444-8444-444444444444"
    attached = [W, foreign, M, None, None, None, [None, ["upload"], [48, 32]]]
    payload = [
        None,
        [[W, None, None, ["original", [1], None, None, M], P]],
        [],
        [[W, 1, "attached", attached]],
    ]
    rows = _media_library(payload, P)
    assert rows[0]["media_id"] == M and "kind" not in rows[0]
    assert rows[1]["media_id"] == W and rows[1]["project_id"] == foreign
    assert rows[1]["attached_to_project_id"] == P and rows[1]["kind"] == "image"
    assert "archived" not in rows[1]


def test_library_refuses_timeline_workflow_conflict():
    from gflow_cli.selfhost.native_worker import _media_library

    payload = [None, [[W, None, None, ["original", [1], None, None, M], P]], [[M, P, M]]]
    with pytest.raises(ValueError, match="contradicts media ownership"):
        _media_library(payload, P)
