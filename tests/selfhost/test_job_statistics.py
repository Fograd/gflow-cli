import time

from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

AUTH = {"Authorization": "Bearer test-token"}


def app(tmp_path):
    return create_app(
        Settings(
            token="test-token",
            root=tmp_path,
            accounts={
                "one": {"email": "account-one", "project": "11111111-1111-4111-8111-111111111111"},
                "two": {"email": "account-two", "project": "22222222-2222-4222-8222-222222222222"},
            },
        ),
        start_workers=False,
    )


def insert(store, profile, kind, state, age=0, duration=10, error=None):
    import json
    from uuid import uuid4

    job = str(uuid4())
    now = time.time()
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                job,
                kind,
                profile,
                "{}",
                state,
                now - age - duration,
                now - age,
                json.dumps({"error": error}) if error else None,
                None,
                "fixture",
            ),
        )
    return job


def test_summary_counts_all_recent_jobs_and_exact_rate_limit_score(tmp_path):
    with TestClient(app(tmp_path)) as client:
        store = client.app.state.store
        for _ in range(105):
            insert(store, "one", "images", "completed", duration=2)
        insert(store, "one", "images", "failed", error={"exit_code": 4})
        insert(store, "one", "images", "failed", error={"exit_code": 10})
        insert(store, "one", "images", "completed", age=901)
        insert(store, "one", "accounts/health", "completed")
        insert(store, "one", "images", "created")
        insert(store, "two", "videos/reference", "running", age=1200)
        response = client.get("/v1/google-flow/jobs?options=summary", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        one = body["images"]["summary"]["account-one"]
        assert one["completed"] == 105
        assert one["failed"] == one["rateLimited"] == 1
        assert one["score"] == 135
        assert body["videos"]["summary"]["account-two"]["executing"] == 1
        assert "executing" not in body["images"]
        assert body["timingPolicy"] == "accepted-to-observation-or-terminal"


def test_executing_and_history_are_safe_bounded_and_averages_weighted(tmp_path):
    with TestClient(app(tmp_path)) as client:
        store = client.app.state.store
        for _ in range(12):
            insert(store, "one", "images", "completed", duration=2)
        insert(store, "one", "videos", "completed", duration=28)
        running = insert(store, "one", "videos/edit", "running", duration=61)
        response = client.get("/v1/google-flow/jobs?options=history", headers=AUTH)
        body = response.json()
        assert len(body["images"]["history"]) == 10
        assert body["videos"]["executing"][running]["elapsed"] == "1:01"
        assert body["combined"]["summary"]["account-one"]["avgResponseTime"] == 4000
        assert set(next(iter(body["images"]["history"].values()))) == {
            "email",
            "timestamp",
            "httpStatus",
            "responseTime",
        }
        with store.connection() as conn:
            conn.execute("UPDATE accounts SET enabled=0 WHERE profile=?", ("one",))
        body = client.get("/v1/google-flow/jobs?options=summary", headers=AUTH).json()
        assert body["emails"] == ["account-two"]
        assert "account-one" not in str(body)


def test_job_statistics_reject_invalid_or_mixed_options_and_preserve_default(tmp_path):
    with TestClient(app(tmp_path)) as client:
        for query in (
            "options=bad",
            "options=summary&limit=2",
            "options=summary&email=account-one",
        ):
            assert client.get("/v1/google-flow/jobs?" + query, headers=AUTH).status_code == 400
        assert "images" in client.get("/v1/google-flow/jobs", headers=AUTH).json()
        assert client.app.state.store.jobs() == []


def test_statistics_window_boundary_and_malformed_rate_limit_code(tmp_path, monkeypatch):
    fixed = time.time()
    monkeypatch.setattr("gflow_cli.selfhost.job_statistics.time.time", lambda: fixed)
    with TestClient(app(tmp_path)) as client:
        store = client.app.state.store
        insert(store, "one", "images", "completed", age=900)
        insert(store, "one", "images", "completed", age=900.001)
        insert(store, "one", "images", "completed", age=-1)
        insert(store, "one", "images", "interrupted", error={"exit_code": 4})
        insert(
            store,
            "one",
            "images",
            "failed",
            error={"exit_code": "4", "detail": "/private/secret-token"},
        )
        body = client.get("/v1/google-flow/jobs?options=history", headers=AUTH).json()
        summary = body["images"]["summary"]["account-one"]
        assert summary["completed"] == 1
        assert summary["failed"] == 2
        assert summary["rateLimited"] == 0
        assert "/private/" not in str(body)
        assert {row["httpStatus"] for row in body["images"]["history"].values()} == {200, 502}
        with store.connection() as conn:
            conn.execute("UPDATE accounts SET verified=0 WHERE profile=?", ("one",))
        body = client.get("/v1/google-flow/jobs?options=executing", headers=AUTH).json()
        assert body["emails"] == ["account-two"]


def test_native_promotion_and_image_upscale_contribute_to_load(tmp_path):
    with TestClient(app(tmp_path)) as client:
        store = client.app.state.store
        promotion = insert(store, "one", "videos/promote", "running")
        upscale = insert(store, "one", "images/upscale", "completed")
        insert(store, "one", "videos/upscale", "completed")
        insert(store, "one", "videos/concatenate", "completed")
        body = client.get("/v1/google-flow/jobs?options=history", headers=AUTH).json()
        assert body["videos"]["summary"]["account-one"]["executing"] == 1
        assert promotion in body["videos"]["executing"]
        assert body["images"]["summary"]["account-one"]["completed"] == 1
        assert upscale in body["images"]["history"]
        assert body["videos"]["summary"]["account-one"]["completed"] == 0
