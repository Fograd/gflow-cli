"""Partial native observations never establish deletion or mutation authority."""

import stat
from copy import deepcopy

import pytest

from gflow_cli.selfhost.native_observations import NativeObservationStore

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"


def history():
    return {
        "workflows": [{"project_id": P, "workflow_id": W}],
        "media": [
            {
                "project_id": P,
                "workflow_id": W,
                "media_id": M,
                "kind": "image",
                "width": 1024,
                "height": 1024,
                "url": "SECRET_URL",
                "caption": "SECRET_CAPTION",
            }
        ],
        "next_cursor": "SECRET_CURSOR",
        "complete": None,
    }


def test_persistent_idempotent_partial_observations_without_private_payloads(tmp_path):
    store = NativeObservationStore(tmp_path)
    result = store.merge_history("pro1", "one", history())
    assert {k: result[k] for k in ("media", "workflows", "projects")} == {
        "media": 1,
        "workflows": 1,
        "projects": 1,
    }
    assert result["complete"] is None
    assert store.merge_history("pro1", "one", history()) == result
    assert store.merge_history("pro1", "one", {"workflows": [], "media": []}) == result
    assert NativeObservationStore(tmp_path).counts("pro1", "one") == result
    assert b"SECRET" not in store.path.read_bytes()
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_account_and_profile_scopes_do_not_mix(tmp_path):
    store = NativeObservationStore(tmp_path)
    store.merge_history("pro1", "one", history())
    assert store.counts("pro1", "two")["media"] == 0
    assert store.counts("pro2", "one")["media"] == 0
    store.merge_history("pro1", "two", history())
    assert store.counts("pro1", "one")["media"] == 1


@pytest.mark.parametrize("field,value", [("project_id", N), ("workflow_id", N), ("kind", "video")])
def test_immutable_known_media_identity_conflicts_roll_back(tmp_path, field, value):
    store = NativeObservationStore(tmp_path)
    store.merge_history("pro1", "one", history())
    data = history()
    data["media"][0][field] = value
    if field in {"project_id", "workflow_id"}:
        data["workflows"][0][field] = value
    with pytest.raises(ValueError):
        store.merge_history("pro1", "one", data)
    assert store.counts("pro1", "one")["media"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "bad_uuid",
        "bool_dimension",
        "missing_workflow",
        "duplicate",
        "bad_timestamp",
        "bad_archived",
    ],
)
def test_entire_snapshot_validates_before_atomic_merge(tmp_path, change):
    store = NativeObservationStore(tmp_path)
    data = history()
    if change == "bad_uuid":
        data["media"][0]["media_id"] = "bad"
    elif change == "bool_dimension":
        data["media"][0]["width"] = True
    elif change == "missing_workflow":
        data["workflows"] = []
    elif change == "duplicate":
        data["media"].append(deepcopy(data["media"][0]))
    elif change == "bad_timestamp":
        data["media"][0]["created_time"] = "now"
    else:
        data["workflows"][0]["archived"] = "false"
    with pytest.raises(ValueError):
        store.merge_history("pro1", "one", data)
    assert store.counts("pro1", "one")["media"] == 0


def test_unknown_kind_is_observation_and_can_gain_or_lose_type(tmp_path):
    store = NativeObservationStore(tmp_path)
    data = history()
    data["media"][0] = {"media_id": M, "project_id": P, "workflow_id": W, "kind": "unknown"}
    store.merge_history("pro1", "one", data)
    store.merge_history("pro1", "one", history())
    store.merge_history("pro1", "one", data)
    assert store.counts("pro1", "one")["media"] == 1


def test_late_conflict_rolls_back_new_rows_and_workflows(tmp_path):
    store = NativeObservationStore(tmp_path)
    store.merge_history("pro1", "one", history())
    data = history()
    data["workflows"].insert(0, {"workflow_id": N, "project_id": P})
    data["media"].insert(0, {"media_id": N, "project_id": P, "workflow_id": N, "kind": "audio"})
    data["media"][1]["kind"] = "video"
    with pytest.raises(ValueError):
        store.merge_history("pro1", "one", data)
    counts = store.counts("pro1", "one")
    assert counts["media"] == counts["workflows"] == 1


def test_metadata_projection_and_latest_unknown_type(tmp_path):
    import json
    import sqlite3
    from contextlib import closing

    store = NativeObservationStore(tmp_path)
    data = history()
    data["media"][0]["created_time"] = "1970-01-01T00:00:00.000000001Z"
    data["workflows"][0]["archived"] = False
    store.merge_history("pro1", "one", data)
    with closing(sqlite3.connect(store.path)) as conn:
        row = json.loads(conn.execute("SELECT metadata FROM media").fetchone()[0])
    assert set(row) == {
        "media_id",
        "project_id",
        "workflow_id",
        "kind",
        "width",
        "height",
        "created_time",
    }
    assert row["created_time"] == "1970-01-01T00:00:00.000000001Z"
    data["media"][0] = {"media_id": M, "project_id": P, "workflow_id": W, "kind": "unknown"}
    store.merge_history("pro1", "one", data)
    with closing(sqlite3.connect(store.path)) as conn:
        row = json.loads(conn.execute("SELECT metadata FROM media").fetchone()[0])
    assert row["kind"] == "unknown" and "width" not in row


@pytest.mark.parametrize("unsafe", ["directory", "file", "symlink"])
def test_observation_storage_refuses_insecure_paths(tmp_path, unsafe):
    if unsafe == "directory":
        tmp_path.chmod(0o755)
    elif unsafe == "file":
        NativeObservationStore(tmp_path)
        (tmp_path / "native_observations.sqlite3").chmod(0o644)
    else:
        target = tmp_path / "target"
        target.touch(mode=0o600)
        (tmp_path / "native_observations.sqlite3").symlink_to(target)
    with pytest.raises(ValueError):
        NativeObservationStore(tmp_path)
