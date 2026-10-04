"""Catalog observations preserve scopes and partial coverage without deletion inference."""

from copy import deepcopy

import pytest

from gflow_cli.selfhost.native_observations import NativeObservationStore

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
Q = "55555555-5555-4555-8555-555555555555"


def catalog():
    return {
        "project_id": P,
        "characters": [
            {"entity_id": E, "project_id": P, "workflow_ids": [W], "display_name": "PRIVATE_NAME"}
        ],
        "user_voices": [
            {
                "ref": M,
                "project_id": P,
                "workflow_id": W,
                "source": "user",
                "dialogue": "PRIVATE_PROMPT",
                "audio_url": "PRIVATE_URL",
            }
        ],
        "media": [{"media_id": Q, "project_id": Q}],
    }


def test_catalog_merge_counts_idempotence_persistence_and_partial_absence(tmp_path):
    store = NativeObservationStore(tmp_path)
    result = store.merge_catalogs("pro1", "one", [catalog(), catalog()])
    assert result["characters"] == result["user_voices"] == result["projects"] == 1
    assert result["media"] == result["workflows"] == 0 and result["complete"] is None
    assert store.merge_catalogs("pro1", "one", []) == result
    assert NativeObservationStore(tmp_path).counts("pro1", "one") == result
    assert b"PRIVATE" not in store.path.read_bytes()
    assert store.counts("pro1", "two")["characters"] == 0
    assert store.counts("pro2", "one")["user_voices"] == 0


def test_empty_observed_project_counts_and_unions_with_history(tmp_path):
    store = NativeObservationStore(tmp_path)
    store.merge_history(
        "pro1", "one", {"workflows": [{"workflow_id": W, "project_id": P}], "media": []}
    )
    result = store.merge_catalogs(
        "pro1", "one", [{"project_id": Q, "characters": [], "user_voices": []}]
    )
    assert result["projects"] == 2
    result = store.merge_catalogs(
        "pro1", "one", [{"project_id": P, "characters": [], "user_voices": []}]
    )
    assert result["projects"] == 2


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_character",
        "foreign_voice",
        "preset",
        "missing_source",
        "bad_workflow",
        "duplicate_conflict",
    ],
)
def test_catalog_whole_batch_validation_precedes_any_write(tmp_path, fault):
    store = NativeObservationStore(tmp_path)
    data = catalog()
    if fault == "foreign_character":
        data["characters"][0]["project_id"] = Q
    elif fault == "foreign_voice":
        data["user_voices"][0]["project_id"] = Q
    elif fault == "preset":
        data["user_voices"][0]["source"] = "system"
    elif fault == "missing_source":
        data["user_voices"][0].pop("source")
    elif fault == "bad_workflow":
        data["characters"][0]["workflow_ids"] = ["bad"]
    else:
        other = deepcopy(data["user_voices"][0])
        other["workflow_id"] = Q
        data["user_voices"].append(other)
    with pytest.raises(ValueError):
        store.merge_catalogs("pro1", "one", [data])
    assert store.counts("pro1", "one")["projects"] == 0


def test_catalog_late_immutable_conflict_rolls_back_new_project(tmp_path):
    store = NativeObservationStore(tmp_path)
    store.merge_catalogs("pro1", "one", [catalog()])
    bad = catalog()
    bad["user_voices"][0]["workflow_id"] = Q
    with pytest.raises(ValueError):
        store.merge_catalogs(
            "pro1", "one", [{"project_id": Q, "characters": [], "user_voices": []}, bad]
        )
    assert store.counts("pro1", "one")["projects"] == 1


def test_character_references_can_change_but_entity_project_cannot(tmp_path):
    store = NativeObservationStore(tmp_path)
    store.merge_catalogs("pro1", "one", [catalog()])
    data = catalog()
    data["characters"][0]["workflow_ids"] = [Q]
    store.merge_catalogs("pro1", "one", [data])
    data["project_id"] = Q
    data["characters"][0]["project_id"] = Q
    data["user_voices"] = []
    with pytest.raises(ValueError):
        store.merge_catalogs("pro1", "one", [data])
