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
