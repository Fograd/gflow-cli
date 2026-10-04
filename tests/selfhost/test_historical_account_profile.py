"""Historical scopes are retired; registration requires a fresh logical profile."""

import time

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_account_scheduler import P, configuration
from tests.selfhost.test_job_statistics import AUTH
from tests.selfhost.test_model_quarantine import DAILY, fail


def test_historical_profile_refuses_registration_atomically(tmp_path):
    store = Store(tmp_path)
    store.account_set("old", "old-public", P, True, True)
    store.account_delete("old")
    with pytest.raises(ValueError, match="historical|Historical"):
        store.account_set("old", "new-public", P, True, True)
    assert store.accounts() == []


def test_new_logical_profile_can_observe_new_quota_without_old_policy_adoption(tmp_path):
    store = Store(tmp_path)
    store.account_set("old", "old-public", P, True, True)
    fail(store, "old", DAILY)
    store.account_delete("old")
    store.account_set("fresh", "new-public", P, True, True)
    fail(store, "fresh", DAILY)
    with store.connection() as conn:
        active = conn.execute(
            "SELECT account FROM model_quarantines WHERE until>?", (time.time(),)
        ).fetchall()
    assert [row[0] for row in active] == ["new-public"]


def test_http_historical_profile_conflict_preserves_existing_browser_directory(
    tmp_path, monkeypatch
):
    browser_root = tmp_path / "browser-profiles"
    old = browser_root / "one"
    fresh = browser_root / "fresh"
    old.mkdir(parents=True)
    fresh.mkdir()
    retained = old / "browser-fixture"
    retained.write_bytes(b"preserved-browser-state")
    monkeypatch.setattr("gflow_cli.auth.default_profile_root", lambda: browser_root)
    monkeypatch.setattr("gflow_cli.auth.profile_dir", lambda name: browser_root / name)
    cfg = configuration(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.delete("/v1/google-flow/accounts/public-one", headers=AUTH)
        assert response.status_code == 200 and response.json()["browserProfileDeleted"] is False
        body = {
            "profile": "one",
            "email": "new-public",
            "projectId": P,
            "enabled": True,
            "verified": True,
        }
        refused = client.post("/v1/google-flow/accounts", headers=AUTH, json=body)
        assert refused.status_code == 409
        assert "one" not in cfg.accounts
        assert client.app.state.store.account_lookup("new-public") is None
        body["profile"] = "fresh"
        accepted = client.post("/v1/google-flow/accounts", headers=AUTH, json=body)
        assert accepted.status_code == 200
        assert cfg.accounts["fresh"]["email"] == "new-public"
        assert retained.read_bytes() == b"preserved-browser-state"
