"""Accepted cookie refresh preserves exact aliases and immutable job audit scopes."""

import pytest

from gflow_cli.selfhost.job_statistics import statistics
from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore
from gflow_cli.selfhost.native_resource_aliases import NativeResourceAlias, NativeResourceAliasStore
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
E = "44444444-4444-4444-8444-444444444444"
A = "user:opaque-email:opaque-image:" + M
C = "user:opaque-email:opaque-character:" + E + "-imgs:1"
V = "user:opaque-email:opaque-voice:" + W + "-mid:" + M


def registries(root):
    store = Store(root)
    store.account_set("original", "alias", P, True, True)
    images = NativeAliasStore(root, resolve_scope=store.resolve_profile_scope)
    resources = NativeResourceAliasStore(root, resolve_scope=store.resolve_profile_scope)
    images.register(NativeAlias(A, "original", "alias", P, M, "image"))
    resources.register(
        NativeResourceAlias(C, "original", "alias", P, "character", E, image_count=1)
    )
    resources.register(NativeResourceAlias(V, "original", "alias", P, "voice", M, workflow_id=W))
    return store, images, resources


def refresh(store, target):
    prior = store.account_lookup("alias")
    store.account_activate_import(target, "alias", P, expected_old=prior)


def test_refresh_keeps_job_audit_and_recent_account_statistics(tmp_path):
    store = Store(tmp_path)
    store.account_set("original", "alias", P, True, True)
    job = store.submit("images", "original", {"prompt": "fixture"}, None)
    store.finish(job["jobId"], "completed", {"media": []})
    before = statistics(store, "summary")["images"]["summary"]["alias"]
    refresh(store, "version")
    after = statistics(store, "summary")["images"]["summary"]["alias"]
    assert before["completed"] == after["completed"] == 1
    with store.connection() as conn:
        assert conn.execute("SELECT profile FROM jobs").fetchone()[0] == "original"


def test_alias_scope_follows_only_committed_same_account_refresh(tmp_path):
    store, images, resources = registries(tmp_path)
    refresh(store, "version")
    refresh(store, "version2")
    assert images.get(A).profile == "version2"
    assert resources.get(C).profile == resources.get(V).profile == "version2"
    # Physical profile origins remain immutable in the exact private alias registries.
    assert NativeAliasStore(tmp_path).get(A).profile == "original"
    assert NativeResourceAliasStore(tmp_path).get(V).profile == "original"
    rebound = images.get(A)
    images.register(rebound)
    resources.register(resources.get(V))
    assert images.remove(A, "version2", "alias")
    assert resources.remove(V, "version2", "alias")


def test_failed_refresh_rolls_back_lineage_account_and_assets(tmp_path):
    store, images, _ = registries(tmp_path)
    store.asset(M, "original", P, "/private/image", "image/png")
    with store.connection() as conn:
        conn.execute(
            "CREATE TRIGGER reject_refresh BEFORE UPDATE ON accounts BEGIN "
            "SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(Exception, match="synthetic failure"):
        refresh(store, "version")
    assert store.account_lookup("alias")["profile"] == "original"
    assert images.get(A).profile == "original"
    assert store.asset_get(M)["profile"] == "original"
    assert store.resolve_profile_scope("original", "alias") == "original"
    with store.connection() as conn:
        assert conn.execute("SELECT count(*) FROM account_profile_lineage").fetchone()[0] == 0


def test_deleted_registration_cannot_be_adopted_by_same_handle_new_profile(tmp_path):
    store, images, resources = registries(tmp_path)
    refresh(store, "version")
    store.account_delete("version")
    # The existing API retains tombstoned rows. Also cover a later physical row cleanup.
    with store.connection() as conn:
        conn.execute("DELETE FROM accounts WHERE enabled=-1")
    store.account_set("unrelated", "alias", P, True, True)
    assert store.resolve_profile_scope("original", "alias") is None
    assert store.resolve_profile_scope("version", "alias") is None
    assert images.get(A).profile == resources.get(V).profile == "original"
    assert store.resolve_profile_scope("unrelated", "alias") == "unrelated"


def test_unrelated_operator_registration_does_not_create_refresh_lineage(tmp_path):
    store, images, _ = registries(tmp_path)
    store.account_delete("original")
    with store.connection() as conn:
        conn.execute("DELETE FROM accounts WHERE enabled=-1")
    store.account_set("unrelated", "alias", P, True, True)
    assert images.get(A).profile == "original"
    assert store.resolve_profile_scope("original", "alias") is None


def test_reused_historical_profile_and_other_account_scope_refuse(tmp_path):
    store, _, _ = registries(tmp_path)
    refresh(store, "version")
    assert store.resolve_profile_scope("original", "other") is None
    with pytest.raises(ValueError, match="historical"):
        refresh(store, "original")


def test_refresh_timestamp_changes_without_changing_creation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr("gflow_cli.selfhost.store.time.time", lambda: 1000.0)
    store.account_set("original", "alias", P, True, True)
    old = store.account_lookup("alias")
    monkeypatch.setattr("gflow_cli.selfhost.store.time.time", lambda: 2000.0)
    refresh(store, "version")
    current = store.account_lookup("alias")
    assert current["created"] == old["created"]
    assert store.account_updated("version", "alias", current["created"]) == 2000.0


def test_same_idempotency_key_reuses_original_job_after_accepted_refresh(tmp_path):
    store = Store(tmp_path)
    store.account_set("original", "alias", P, True, True)
    payload = {"prompt": "same", "project": P, "_delivery_async": False}
    job = store.submit("images", "original", payload, "same-key")
    store.finish(job["jobId"], "completed", {"media": []})
    refresh(store, "version")
    replay = store.submit("images", "version", {**payload, "_delivery_async": True}, "same-key")
    assert replay["jobId"] == job["jobId"] and replay["status"] == "completed"
    assert len(store.jobs()) == 1
    with store.connection() as conn:
        assert conn.execute("SELECT profile FROM jobs").fetchone()[0] == "original"


def test_refresh_idempotency_refuses_changed_payload_or_unrelated_registration(tmp_path):
    store = Store(tmp_path)
    store.account_set("original", "alias", P, True, True)
    payload = {"prompt": "same", "project": P}
    job = store.submit("images", "original", payload, "same-key")
    store.finish(job["jobId"], "completed", {"media": []})
    refresh(store, "version")
    with pytest.raises(ValueError):
        store.submit("images", "version", {**payload, "prompt": "changed"}, "same-key")
    store.account_delete("version")
    with store.connection() as conn:
        conn.execute("DELETE FROM accounts WHERE enabled=-1")
    store.account_set("unrelated", "alias", P, True, True)
    with pytest.raises(ValueError):
        store.submit("images", "unrelated", payload, "same-key")
    assert len(store.jobs()) == 1
