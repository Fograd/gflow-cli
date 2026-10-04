"""Automatic generation selection consumes local quota observations before queueing."""

import time

from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_account_scheduler import configuration, selected
from tests.selfhost.test_job_statistics import AUTH
from tests.selfhost.test_model_quarantine import THROTTLE, fail


def quarantine(store, profile):
    fail(store, profile, THROTTLE, model=None)
    with store.connection() as conn:
        conn.execute("UPDATE jobs SET updated=?", (time.time() - 901,))


def test_automatic_images_avoid_active_global_quarantine(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        quarantine(client.app.state.store, "one")
        assert selected(client, {}) == "two"


def test_all_quarantined_returns_policy_retry_before_creating_job(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        quarantine(store, "one")
        quarantine(store, "two")
        before = len(store.jobs())
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "fixture", "async": True},
        )
        assert response.status_code == 429
        detail = response.json()
        assert detail["code"] == "local_quota_policy"
        assert detail["error"] == "no_eligible_account"
        assert detail["policy"] == "useapi-compatible-local-policy-v1"
        assert int(response.headers["Retry-After"]) == detail["retryAfter"] > 0
        assert len(detail["skipReasons"]) == 2
        assert len(store.jobs()) == before


def test_pinned_generation_and_metadata_reads_bypass_quarantine(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        quarantine(store, "one")
        quarantine(store, "two")
        assert selected(client, {"email": "public-one"}) == "one"
        response = client.get("/v1/google-flow/accounts", headers=AUTH)
        assert response.status_code == 200


def test_single_valid_account_retains_explicit_local_policy_exception(tmp_path):
    cfg = configuration(tmp_path)
    cfg.accounts.pop("two")
    with TestClient(create_app(cfg, start_workers=False)) as client:
        quarantine(client.app.state.store, "one")
        assert selected(client, {}) == "one"
