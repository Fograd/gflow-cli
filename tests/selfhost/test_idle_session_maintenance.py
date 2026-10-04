"""Offline maintenance admission and lifecycle, never real browser access."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.session_health import health_observation
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
INTERVAL = 1800


@pytest.fixture
def case(tmp_path, monkeypatch):
    clock = [1_800_000_000.0]
    monkeypatch.setattr("gflow_cli.selfhost.store.time.time", lambda: clock[0])
    cfg = Settings(
        token="fixture",
        root=tmp_path,
        accounts={
            "pro2": {"email": "test-account", "project": P},
            "pro3": {"email": "other-account", "project": OTHER},
        },
    )
    store = Store(tmp_path)
    store.account_seed(cfg.accounts)
    clock[0] += INTERVAL
    return cfg, store, clock


def test_interval_default_is_disabled(tmp_path):
    cfg = Settings(token="fixture", root=tmp_path, accounts={})
    assert getattr(cfg, "idle_session_interval", None) == 0


@pytest.mark.parametrize("value", [True, "1800", -1, 1, 1799, float("nan"), float("inf")])
def test_interval_rejects_unsafe_or_rapid_values(tmp_path, value):
    with pytest.raises(ValueError, match="Idle session interval"):
        Settings(token="fixture", root=tmp_path, accounts={}, idle_session_interval=value)


def test_interval_environment_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("GFLOW_DAEMON_TOKEN", "fixture")
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    monkeypatch.setenv("GFLOW_SELFHOST_IDLE_SESSION_INTERVAL_SECONDS", "1800")
    assert Settings.environment().idle_session_interval == INTERVAL


def test_due_idle_queues_existing_health_once_and_survives_restart(case):
    cfg, store, clock = case
    assert store.enqueue_idle_health("pro2", INTERVAL) is True
    assert store.enqueue_idle_health("pro2", INTERVAL) is False
    assert Store(cfg.root).enqueue_idle_health("pro2", INTERVAL) is False
    rows = store.jobs()
    assert len(rows) == 1
    job = store.claim("pro2")
    assert job["kind"] == "accounts/health"
    payload = json.loads(job["payload"])
    assert payload["project"] == P and payload["_idle_session_maintenance"] is True
    store.finish(
        job["id"],
        "completed",
        {"sessionHealth": health_observation("OK", "project_access_verified")},
    )
    status = store.idle_session_status("pro2", INTERVAL)
    assert status["nextDueAt"] == clock[0] + INTERVAL
    assert Store(cfg.root).enqueue_idle_health("pro2", INTERVAL) is False
    clock[0] += INTERVAL
    assert store.enqueue_idle_health("pro2", INTERVAL) is True


def test_concurrent_admission_and_global_single_outstanding(case):
    _, store, _ = case
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(lambda _: store.enqueue_idle_health("pro2", INTERVAL), range(4)))
    assert accepted.count(True) == 1
    assert store.enqueue_idle_health("pro3", INTERVAL) is False
    assert len(store.jobs()) == 1


@pytest.mark.parametrize("kind", ["images", "accounts/health"])
@pytest.mark.parametrize("running", [False, True])
def test_busy_profile_never_admits_maintenance(case, kind, running):
    _, store, _ = case
    existing = store.submit(kind, "pro2", {"project": P}, None)
    if running:
        store.claim("pro2")
    assert store.enqueue_idle_health("pro2", INTERVAL) is False
    assert store.jobs()[0]["jobId"] == existing["jobId"]


@pytest.mark.parametrize(
    "state", ["disabled", "unverified", "removed", "missing", "interval_zero", "not_due"]
)
def test_ineligible_profiles_never_queue(case, state):
    _, store, clock = case
    profile = "pro1" if state == "missing" else "pro2"
    if state == "disabled":
        store.account_set("pro2", "test-account", P, False, True)
    elif state == "unverified":
        store.account_set("pro2", "test-account", P, True, False)
    elif state == "removed":
        store.account_delete("pro2")
    elif state == "not_due":
        clock[0] -= 1
    assert store.enqueue_idle_health(profile, 0 if state == "interval_zero" else INTERVAL) is False
    assert store.jobs() == []


@pytest.mark.parametrize("health,multiplier", [("OK", 1), ("UNKNOWN", 2), ("LOGIN_REQUIRED", 4)])
def test_health_backoff_is_persisted_and_not_login_or_generation(case, health, multiplier):
    _, store, clock = case
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    reason = (
        "project_access_verified"
        if health == "OK"
        else "login_required"
        if health == "LOGIN_REQUIRED"
        else "probe_error"
    )
    store.finish(job["id"], "completed", {"sessionHealth": health_observation(health, reason)})
    status = store.idle_session_status("pro2", INTERVAL)
    assert status["nextDueAt"] == clock[0] + INTERVAL * multiplier
    clock[0] += INTERVAL * multiplier - 1
    assert store.enqueue_idle_health("pro2", INTERVAL) is False
    clock[0] += 1
    assert store.enqueue_idle_health("pro2", INTERVAL) is True
    assert all(row["kind"] == "accounts/health" for row in _rows(store))


def _rows(store):
    with store.connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM jobs")]


def test_long_interval_backoff_never_shortens_interval(case):
    _, store, clock = case
    clock[0] += 172800
    assert store.enqueue_idle_health("pro2", 172800)
    job = store.claim("pro2")
    store.finish(job["id"], "completed", {"sessionHealth": health_observation()})
    assert store.idle_session_status("pro2", 172800)["nextDueAt"] == clock[0] + 172800


def test_mapping_change_and_reversion_do_not_inherit_due_or_health(case):
    _, store, clock = case
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    store.finish(
        job["id"],
        "completed",
        {"sessionHealth": health_observation("OK", "project_access_verified")},
    )
    store.account_set("pro2", "test-account", OTHER, True, True)
    store.account_set("pro2", "test-account", P, True, True)
    status = store.idle_session_status("pro2", INTERVAL)
    assert status["lastObservation"] is None and status["lastJobId"] is None
    assert store.enqueue_idle_health("pro2", INTERVAL) is True


def test_interval_disable_cancels_only_created_maintenance(case):
    cfg, store, _ = case
    store.enqueue_idle_health("pro2", INTERVAL)
    maintenance = store.jobs()[0]
    manual = store.submit("accounts/health", "pro3", {"project": OTHER}, None)
    generation = store.submit("images", "pro3", {"project": OTHER}, None)
    assert store.cancel_idle_health(0, cfg.accounts) == 1
    assert store.get(maintenance["jobId"]).get("idleSessionMaintenanceCancelled") is True
    assert store.get(manual["jobId"])["status"] == "created"
    assert store.get(generation["jobId"])["status"] == "created"
    assert store.idle_session_status("pro2", 0)["lastObservation"] is None


def test_disable_never_cancels_active_read(case):
    cfg, store, _ = case
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    assert store.cancel_idle_health(0, cfg.accounts) == 0
    assert store.get(job["id"])["status"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["interval", "account", "project", "scope"])
async def test_execution_rechecks_before_native_subprocess(case, monkeypatch, changed):
    from gflow_cli.selfhost.runtime import execute

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    if changed == "interval":
        cfg.idle_session_interval = 0
    elif changed == "account":
        store.account_set("pro2", "test-account", P, False, True)
    elif changed == "project":
        store.account_set("pro2", "test-account", OTHER, True, True)
    else:
        payload = json.loads(job["payload"])
        payload["_idle_session_scope"] = "stale"
        job["payload"] = json.dumps(payload)
    run = AsyncMock(side_effect=AssertionError("No native operation authorized"))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    run.assert_not_awaited()
    assert result["idleSessionMaintenanceCancelled"] is True
    assert "sessionHealth" not in result


def test_account_metadata_reports_observations_separately_and_privately(case):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import create_app

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    observation = health_observation()
    observation["cookie"] = "private-cookie"
    store.finish(job["id"], "completed", {"sessionHealth": observation})
    with TestClient(create_app(cfg, start_workers=False)) as client:
        assert client.get("/v1/google-flow/accounts").status_code == 401
        result = client.get(
            "/v1/google-flow/accounts", headers={"Authorization": "Bearer fixture"}
        ).json()
    maintenance = result["test-account"]["idleSessionMaintenance"]
    assert result["test-account"]["health"] == "OK"
    assert maintenance["lastObservation"]["health"] == "UNKNOWN"
    assert maintenance["refreshAttempted"] is False
    assert "private-cookie" not in repr(maintenance)
    assert "test-account" not in repr(maintenance)


@pytest.mark.asyncio
async def test_scheduler_cancellation_exits_without_browser_or_replay(case, monkeypatch):
    from gflow_cli.selfhost import idle_session

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    sleeping = asyncio.Event()

    async def wait(_):
        sleeping.set()
        await asyncio.Future()

    monkeypatch.setattr(idle_session.asyncio, "sleep", wait)
    task = asyncio.create_task(idle_session.maintain_idle_sessions(cfg, store))
    await sleeping.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(store.jobs()) == 1
    assert _rows(store)[0]["kind"] == "accounts/health"


@pytest.mark.asyncio
async def test_mapping_reversion_cannot_reauthorize_previously_queued_read(case, monkeypatch):
    from gflow_cli.selfhost.runtime import execute

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    store.account_set("pro2", "test-account", OTHER, True, True)
    store.account_set("pro2", "test-account", P, True, True)
    run = AsyncMock(side_effect=AssertionError("Stale queued read"))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    assert (await execute(cfg, store, job))["idleSessionMaintenanceCancelled"] is True
    run.assert_not_awaited()


def test_mapping_reversion_cancels_stale_created_maintenance(case):
    cfg, store, _ = case
    store.enqueue_idle_health("pro2", INTERVAL)
    store.account_set("pro2", "test-account", OTHER, True, True)
    store.account_set("pro2", "test-account", P, True, True)
    assert store.cancel_idle_health(INTERVAL, cfg.accounts) == 1


@pytest.mark.asyncio
async def test_lifespan_cancels_disabled_reads_before_workers_and_stops_tasks(case, monkeypatch):
    from gflow_cli.selfhost.server import create_app

    cfg, store, _ = case
    store.enqueue_idle_health("pro2", INTERVAL)
    job_id = store.jobs()[0]["jobId"]
    entered = asyncio.Event()
    closed = []

    async def worker(*_):
        assert store.get(job_id).get("idleSessionMaintenanceCancelled") is True
        entered.set()
        try:
            await asyncio.Future()
        finally:
            closed.append("worker")

    async def callbacks(*_):
        try:
            await asyncio.Future()
        finally:
            closed.append("callbacks")

    monkeypatch.setattr("gflow_cli.selfhost.server.worker", worker)
    monkeypatch.setattr("gflow_cli.selfhost.server.deliver_callbacks", callbacks)
    app = create_app(cfg)
    async with app.router.lifespan_context(app):
        await entered.wait()
    assert sorted(closed) == ["callbacks", "worker", "worker"]


def test_disabled_account_http_stops_only_queued_maintenance(case, monkeypatch):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import create_app

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    target = cfg.root / "profile_pro2"
    target.mkdir()
    monkeypatch.setattr("gflow_cli.auth.profile_dir", lambda _: target)
    monkeypatch.setattr("gflow_cli.auth.default_profile_root", lambda: cfg.root)
    store.enqueue_idle_health("pro2", INTERVAL)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/accounts",
            headers={"Authorization": "Bearer fixture"},
            json={
                "profile": "pro2",
                "email": "test-account",
                "projectId": P,
                "enabled": False,
                "verified": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["idleSessionMaintenance"]["enabled"] is False
    assert store.accounts()[0]["enabled"] == 0


@pytest.mark.asyncio
async def test_enabled_lifespan_starts_scheduler_and_joins_it_on_shutdown(case, monkeypatch):
    from gflow_cli.selfhost import idle_session
    from gflow_cli.selfhost.server import create_app

    cfg, store, _ = case
    cfg.idle_session_interval = INTERVAL
    entered = asyncio.Event()
    closed = []
    original = idle_session.maintain_idle_sessions

    async def scheduler(*args):
        entered.set()
        try:
            await original(*args)
        finally:
            closed.append("maintenance")

    async def wait(*_):
        await asyncio.Future()

    monkeypatch.setattr(idle_session, "maintain_idle_sessions", scheduler)
    monkeypatch.setattr("gflow_cli.selfhost.server.worker", wait)
    monkeypatch.setattr("gflow_cli.selfhost.server.deliver_callbacks", wait)
    app = create_app(cfg)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(entered.wait(), 1)
        assert len(store.jobs()) == 1
        assert _rows(store)[0]["kind"] == "accounts/health"
    assert closed == ["maintenance"]


@pytest.mark.asyncio
async def test_profile_lease_contention_is_unknown_and_backs_off(case, monkeypatch):
    from gflow_cli.selfhost.runtime import execute

    cfg, store, clock = case
    cfg.idle_session_interval = INTERVAL
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    run = AsyncMock(
        return_value=(
            0,
            json.dumps(
                {"status": "ok", "sessionHealth": health_observation(reason="profile_busy")}
            ).encode(),
        )
    )
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    run.assert_awaited_once()
    assert run.await_args.args[0][3] == "session-health"
    store.finish(job["id"], "completed", result)
    status = store.idle_session_status("pro2", INTERVAL)
    assert status["lastObservation"]["reason"] == "profile_busy"
    assert status["nextDueAt"] == clock[0] + 2 * INTERVAL


def test_upgrade_existing_queue_and_recover_maintenance_without_replay(case):
    cfg, store, clock = case
    with store.connection() as conn:
        conn.execute("DROP TABLE idle_session_maintenance")
        conn.execute("PRAGMA user_version=4")
    store = Store(cfg.root)
    with store.connection() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    store.enqueue_idle_health("pro2", INTERVAL)
    job = store.claim("pro2")
    Store(cfg.root).recover()
    assert store.get(job["id"])["sessionHealth"]["reason"] == "interrupted"
    assert store.enqueue_idle_health("pro2", INTERVAL) is False
    assert store.idle_session_status("pro2", INTERVAL)["nextDueAt"] == clock[0] + 2 * INTERVAL
