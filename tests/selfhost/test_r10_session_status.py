"""R10 actual-identity, registration epoch, status freshness and maintenance regressions."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.selfhost.session_health import health_observation, probe_project_access
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PRINCIPAL = "original@example.test"
DIGEST = hashlib.sha256(PRINCIPAL.encode()).hexdigest()


@pytest.fixture
def browser(tmp_path, monkeypatch):
    target = tmp_path / "profile_fixture"
    target.mkdir()
    (target / ".gflow_account").write_text(PRINCIPAL)
    monkeypatch.setattr("gflow_cli.selfhost.session_health.profile_dir", lambda _: target)
    monkeypatch.setattr("gflow_cli.selfhost.session_health.default_profile_root", lambda: tmp_path)
    identity = AsyncMock(return_value=PRINCIPAL)
    monkeypatch.setattr("gflow_cli.auth.native_identity.read_native_identity", identity)
    access = AsyncMock(return_value={"private": "timeline"})
    context = AsyncMock()
    page = object()
    context.__aenter__.return_value = SimpleNamespace(
        _page=page, list_native_media=access, browser_teardown_succeeded=True
    )
    factory = Mock(return_value=context)
    monkeypatch.setattr("gflow_cli.api.client.FlowApiClient", factory)
    return target, identity, access, context, factory


@pytest.mark.asyncio
async def test_wrong_google_principal_cannot_pass_project_health(browser):
    _, identity, access, _, _ = browser
    identity.return_value = "wrong@example.test"
    result = await probe_project_access("fixture", P)
    assert result["health"] == "UNKNOWN" and result["reason"] == "identity_changed"
    access.assert_not_awaited()
    assert "wrong@example" not in repr(result)


@pytest.mark.asyncio
async def test_real_principal_is_verified_on_both_sides_of_project_read(browser):
    _, identity, access, _, _ = browser
    result = await probe_project_access("fixture", P)
    assert result["identityVerified"] is True and result["health"] == "OK"
    assert identity.await_count == 2
    access.assert_awaited_once_with(P)


@pytest.mark.asyncio
async def test_google_switch_during_project_read_is_not_ok(browser):
    _, identity, _, _, _ = browser
    identity.side_effect = [PRINCIPAL, "wrong@example.test"]
    result = await probe_project_access("fixture", P)
    assert result["health"] == "UNKNOWN" and result["reason"] == "identity_changed"


@pytest.mark.asyncio
async def test_matching_changed_marker_does_not_redefine_expected_account(browser):
    target, identity, access, _, factory = browser
    (target / ".gflow_account").write_text("changed@example.test")
    identity.return_value = "changed@example.test"
    result = await probe_project_access("fixture", P, expected_identity_sha256=DIGEST)
    assert result["reason"] == "identity_changed"
    access.assert_not_awaited()
    factory.assert_not_called()


@pytest.fixture
def status_case(tmp_path, monkeypatch):
    # Use a deterministic clock without manufacturing future observation stamps.
    clock = [datetime.now(UTC).timestamp()]
    monkeypatch.setattr("gflow_cli.selfhost.store.time.time", lambda: clock[0])

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(clock[0], tz)

    monkeypatch.setattr("gflow_cli.selfhost.session_health.datetime", ClockDateTime)
    monkeypatch.setattr(
        "gflow_cli.selfhost.session_status.profile_identity_sha256", lambda _: DIGEST
    )
    store = Store(tmp_path)
    store.account_seed(
        {
            "fixture": {"email": "public-handle", "project": P},
            "other": {"email": "other-handle", "project": OTHER},
        }
    )
    return store, clock


def complete(store, clock, health="OK", reason="project_access_verified", identity=True):
    accepted = store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    observation = health_observation(health, reason)
    observation["checkedAt"] = datetime.fromtimestamp(clock[0], UTC).isoformat()
    observation["identityVerified"] = identity
    store.finish(job["id"], "completed", {"sessionHealth": observation})
    return accepted, observation


def test_last_success_survives_interrupted_check_and_restart(status_case):
    store, clock = status_case
    complete(store, clock)
    successful_at = store.session_status("fixture", 1800)["lastVerifiedAccessAt"]
    clock[0] += 10
    store.submit("accounts/health", "fixture", {"project": P}, None)
    store.claim("fixture")
    Store(store.root).recover()
    status = Store(store.root).session_status("fixture", 1800)
    assert status["latestObservation"]["reason"] == "interrupted"
    assert status["lastVerifiedAccessAt"] == successful_at
    assert status["lastVerifiedIdentityAt"] is not None
    assert status["state"] == "unknown" and status["loginRequired"] is False


def test_stale_success_is_historical_not_current_or_login_required(status_case):
    store, clock = status_case
    complete(store, clock)
    clock[0] += 3601
    status = store.session_status("fixture", 1800)
    assert status["state"] == "stale" and status["fresh"] is False
    assert status["lastVerifiedAccessAt"] is not None and status["loginRequired"] is False
    assert status["renewal"]["state"] == "unproved"
    assert status["renewal"]["lastAttemptAt"] is None


@pytest.mark.parametrize(
    "health,reason,factor",
    [("UNKNOWN", "profile_busy", 2), ("LOGIN_REQUIRED", "login_required", 4)],
)
def test_manual_observation_drives_scheduler_backoff_and_recovery(
    status_case, health, reason, factor
):
    store, clock = status_case
    clock[0] += 1800
    assert store.enqueue_idle_health("fixture", 1800)
    job = store.claim("fixture")
    store.finish(
        job["id"],
        "completed",
        {"sessionHealth": health_observation("OK", "project_access_verified")},
    )
    clock[0] += 10
    complete(store, clock, health, reason, identity=False)
    assert store.idle_session_status("fixture", 1800)["nextDueAt"] == clock[0] + 1800 * factor
    assert store.session_status("fixture", 1800)["loginRequired"] is (health == "LOGIN_REQUIRED")
    clock[0] += 10
    complete(store, clock)
    assert store.session_status("fixture", 1800)["state"] == "verified"
    assert store.idle_session_status("fixture", 1800)["nextDueAt"] == clock[0] + 1800


def test_mapping_reversion_cannot_resurrect_active_health(status_case):
    store, clock = status_case
    complete(store, clock)
    pending = store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    original_scope = json.loads(job["payload"]).get("_session_scope")
    assert original_scope
    store.account_set("fixture", "public-handle", OTHER, True, True)
    store.account_set("fixture", "public-handle", P, True, True)
    store.finish(
        pending["jobId"],
        "completed",
        {"sessionHealth": health_observation("OK", "project_access_verified")},
    )
    status = store.session_status("fixture", 1800)
    assert status["lastVerifiedAccessAt"] is None
    assert status["state"] == "unobserved"
    assert store.health_job_current(job) is False


def test_duplicate_completion_does_not_refresh_status_or_backoff(status_case):
    store, clock = status_case
    accepted, _ = complete(store, clock)
    before = store.session_status("fixture", 1800)
    due = store.idle_session_status("fixture", 1800)["nextDueAt"]
    clock[0] += 100
    store.finish(
        accepted["jobId"],
        "completed",
        {"sessionHealth": health_observation("LOGIN_REQUIRED", "login_required")},
    )
    after = store.session_status("fixture", 1800)
    assert after["latestObservation"] == before["latestObservation"]
    assert store.idle_session_status("fixture", 1800)["nextDueAt"] == due


@pytest.mark.parametrize("stamp", ["bad", "2099-01-01T00:00:00Z", "2000-01-01T00:00:00Z"])
def test_unbound_worker_timestamp_cannot_manufacture_access(status_case, stamp):
    store, _ = status_case
    store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    observation = health_observation("OK", "project_access_verified")
    observation.update(checkedAt=stamp, identityVerified=True)
    store.finish(job["id"], "completed", {"sessionHealth": observation})
    status = store.session_status("fixture", 1800)
    assert status["lastVerifiedAccessAt"] is None and status["state"] == "unknown"


def test_status_is_scoped_private_and_disabled_profile_is_not_read(status_case, monkeypatch):
    store, clock = status_case
    complete(store, clock)
    other = store.session_status("other", 1800)
    assert other["lastVerifiedAccessAt"] is None
    store.account_set("fixture", "public-handle", P, False, True)
    monkeypatch.setattr(
        "gflow_cli.selfhost.session_health.read_verified_account",
        Mock(side_effect=AssertionError("disabled profile opened")),
    )
    status = store.session_status("fixture", 1800)
    assert status["state"] == "disabled" and status["loginRequired"] is False
    assert "public-handle" not in repr(status) and DIGEST not in repr(status)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,health", [(401, "LOGIN_REQUIRED"), (403, "UNKNOWN"), (500, "UNKNOWN")]
)
async def test_only_exact_identity_unauthenticated_http_means_login(browser, status, health):
    from gflow_cli.api.transports.migrated_rpc import native_rpc

    _, identity, _, _, _ = browser
    # Exercise the real HTTP classifier, rather than manufacturing an auth error.
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": status, "text": ""}))

    async def refused(_):
        return await native_rpc(page, "o30O0e", [], "/u/0/", require_single=True)

    identity.side_effect = refused
    result = await probe_project_access("fixture", P)
    assert result["health"] == health
    assert result["identityVerified"] is False


@pytest.mark.asyncio
async def test_correlated_principal_unauthenticated_rpc_is_login_required(browser):
    from gflow_cli.api.transports.migrated_rpc import NativeMetadataRpcError

    _, identity, _, _, _ = browser
    identity.side_effect = NativeMetadataRpcError("o30O0e", 16)
    result = await probe_project_access("fixture", P)
    assert result["health"] == "LOGIN_REQUIRED" and result["reason"] == "login_required"


@pytest.mark.parametrize("pending", [False, True])
def test_enable_reversion_cannot_restore_old_maintenance_status(status_case, pending):
    store, clock = status_case
    clock[0] += 1800
    assert store.enqueue_idle_health("fixture", 1800)
    if not pending:
        job = store.claim("fixture")
        store.finish(
            job["id"],
            "completed",
            {"sessionHealth": health_observation("LOGIN_REQUIRED", "login_required")},
        )
    store.account_set("fixture", "public-handle", P, False, True)
    store.account_set("fixture", "public-handle", P, True, True)
    status = store.idle_session_status("fixture", 1800)
    assert status["lastObservation"] is None and status["lastJobId"] is None
    assert status["state"] != "pending"


@pytest.mark.parametrize(
    "health,reason", [("LOGIN_REQUIRED", "profile_busy"), ("UNKNOWN", "login_required")]
)
def test_malformed_auth_status_pair_cannot_claim_login_required(health, reason):
    from gflow_cli.selfhost.session_health import public_health_observation

    result = public_health_observation(health_observation(health, reason))
    assert result["health"] == "UNKNOWN" and result["reason"] == "probe_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["context", "driver"])
async def test_actual_client_suppressed_teardown_failure_is_not_healthy(
    tmp_path, monkeypatch, failure
):
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.profile_lease import ProfileLease

    target = tmp_path / "profile_fixture"
    target.mkdir()
    (target / ".gflow_account").write_text(PRINCIPAL)
    monkeypatch.setattr("gflow_cli.selfhost.session_health.profile_dir", lambda _: target)
    monkeypatch.setattr("gflow_cli.selfhost.session_health.default_profile_root", lambda: tmp_path)
    monkeypatch.setattr(
        "gflow_cli.auth.native_identity.read_native_identity", AsyncMock(return_value=PRINCIPAL)
    )
    browser_context = SimpleNamespace(close=AsyncMock(), browser=None)
    driver = SimpleNamespace(stop=AsyncMock())
    if failure == "context":
        browser_context.close.side_effect = RuntimeError("private-close")
    else:
        driver.stop.side_effect = RuntimeError("private-driver")

    async def enter(client):
        client._context = browser_context
        client._page = object()
        client._pw = driver
        client._lease = ProfileLease(target).acquire()
        return client

    monkeypatch.setattr(FlowApiClient, "__aenter__", enter)
    monkeypatch.setattr(FlowApiClient, "list_native_media", AsyncMock(return_value={}))
    # Actual __aexit__ suppresses exceptions; the probe must inspect its explicit outcome.
    result = await probe_project_access("fixture", P)
    assert result["health"] == "UNKNOWN" and result["reason"] == "cleanup_incomplete"
    assert result["identityVerified"] is False
    driver.stop.assert_awaited_once()
    with ProfileLease(target):
        pass  # All release steps still ran; we never defeat a competing lease.


def test_store_keeps_original_principal_anchor_after_marker_change_and_restart(
    status_case, monkeypatch
):
    store, clock = status_case
    complete(store, clock)
    monkeypatch.setattr(
        "gflow_cli.selfhost.session_status.profile_identity_sha256",
        lambda _: hashlib.sha256(b"changed@example.test").hexdigest(),
    )
    store = Store(store.root)
    store.account_set("fixture", "public-handle", P, False, True)
    store.account_set("fixture", "public-handle", P, True, True)
    store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    assert json.loads(job["payload"])["_expected_identity_sha256"] == DIGEST
    assert store.health_job_current(job) is True
