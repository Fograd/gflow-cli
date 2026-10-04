"""Automatic account routing uses the public rolling score without rerouting pinned inputs."""

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_job_statistics import AUTH, insert

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"


def configuration(root):
    return Settings(
        token="test-token",
        root=root,
        sync_wait=0,
        accounts={
            "one": {"email": "public-one", "project": P},
            "two": {"email": "public-two", "project": Q},
        },
    )


def selected(client, body):
    response = client.post(
        "/v1/google-flow/images", headers=AUTH, json={"prompt": "fixture", "async": True, **body}
    )
    assert response.status_code == 201, response.text
    with client.app.state.store.connection() as conn:
        return conn.execute(
            "SELECT profile FROM jobs WHERE id=?", (response.json()["jobId"],)
        ).fetchone()[0]


def test_automatic_http_selection_penalizes_recent_completion_and_cross_family_failure(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        insert(store, "one", "videos", "failed", error={"exit_code": 1})
        insert(store, "two", "images", "completed")
        assert selected(client, {}) == "two"


def test_automatic_http_selection_uses_recent_completed_score_before_queue_load(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        insert(store, "one", "images", "completed")
        insert(store, "two", "images", "created")
        assert selected(client, {}) == "two"


@pytest.mark.parametrize("pinned", ["email", "managed", "native"])
def test_pinned_http_account_and_reference_scope_ignore_automatic_score(tmp_path, pinned):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        insert(store, "one", "images", "failed", error={"exit_code": 4})
        body = {"email": "public-one"}
        if pinned == "managed":
            store.asset(M, "one", P, str(tmp_path / "image.jpg"), "image/jpeg")
            body = {"reference_1": M}
        elif pinned == "native":
            body["reference_1"] = M
        assert selected(client, body) == "one"


def test_pinned_mixed_reference_scope_refuses_instead_of_rerouting(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        store.asset(M, "one", P, str(tmp_path / "image.jpg"), "image/jpeg")
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "fixture", "async": True, "email": "public-two", "reference_1": M},
        )
        assert response.status_code == 422
        assert store.jobs() == []


def test_scheduler_reuses_exact_public_score_weights_and_queue_tie(tmp_path):
    from gflow_cli.selfhost.account_scheduler import select_account
    from gflow_cli.selfhost.store import Store

    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    insert(store, "one", "images", "failed", error={"exit_code": 4})
    insert(store, "two", "videos", "failed", error={"exit_code": 1})
    assert select_account(store, cfg.accounts) == "two"
    # Lower-ranked families are not quarantined from arbitrary reason strings.
    with store.connection() as conn:
        conn.execute("DELETE FROM jobs")
    insert(store, "one", "images", "created")
    assert select_account(store, cfg.accounts) == "two"


def test_stale_terminal_score_expires_after_exact_fifteen_minute_window(tmp_path, monkeypatch):
    from gflow_cli.selfhost.account_scheduler import select_account
    from gflow_cli.selfhost.store import Store

    now = 10000.0
    monkeypatch.setattr("gflow_cli.selfhost.job_statistics.time.time", lambda: now)
    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    insert(store, "one", "images", "failed", age=899, error={"exit_code": 4})
    insert(store, "two", "videos", "completed")
    assert select_account(store, cfg.accounts) == "two"
    now += 2
    assert select_account(store, cfg.accounts) == "one"


def test_accepted_refresh_lineage_contributes_old_jobs_to_current_account(tmp_path):
    from gflow_cli.selfhost.account_scheduler import select_account
    from gflow_cli.selfhost.store import Store

    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    insert(store, "one", "images", "completed")
    before = store.account_lookup("public-one")
    store.account_activate_import("version", "public-one", P, expected_old=before)
    cfg.accounts["version"] = cfg.accounts.pop("one")
    assert select_account(store, cfg.accounts) == "two"
    with store.connection() as conn:
        assert conn.execute("SELECT profile FROM jobs").fetchone()[0] == "one"


def test_stale_configuration_unverified_or_disabled_account_is_not_automatic_candidate(tmp_path):
    from gflow_cli.selfhost.account_scheduler import select_account
    from gflow_cli.selfhost.store import Store

    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    with store.connection() as conn:
        conn.execute("UPDATE accounts SET verified=0 WHERE profile='one'")
    assert select_account(store, cfg.accounts) == "two"
    with store.connection() as conn:
        conn.execute("UPDATE accounts SET enabled=0 WHERE profile='two'")
    with pytest.raises(ValueError, match="verified"):
        select_account(store, cfg.accounts)


def test_scheduler_does_not_rebind_stale_profile_by_matching_public_handle(tmp_path):
    from gflow_cli.selfhost.account_scheduler import select_account
    from gflow_cli.selfhost.store import Store

    cfg = configuration(tmp_path)
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    before = store.account_lookup("public-one")
    store.account_activate_import("version", "public-one", P, expected_old=before)
    with store.connection() as conn:
        conn.execute("UPDATE accounts SET enabled=0 WHERE profile='two'")
    with pytest.raises(ValueError, match="verified"):
        select_account(store, cfg.accounts)


def test_http_no_current_verified_automatic_candidate_returns_503_and_does_not_enqueue(tmp_path):
    with TestClient(create_app(configuration(tmp_path), start_workers=False)) as client:
        with client.app.state.store.connection() as conn:
            conn.execute("UPDATE accounts SET verified=0")
        response = client.post(
            "/v1/google-flow/images", headers=AUTH, json={"prompt": "fixture", "async": True}
        )
        assert response.status_code == 503
        assert client.app.state.store.jobs() == []
