"""Native access health reports evidence at one time, never refreshes authentication."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.errors import AuthMissingError, ProfileLockedError
from gflow_cli.selfhost.session_health import probe_project_access

P = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def probe(tmp_path, monkeypatch):
    target = tmp_path / "profile_fixture"
    target.mkdir()
    (target / ".gflow_account").write_text("fixture@example.test")
    monkeypatch.setattr("gflow_cli.selfhost.session_health.profile_dir", lambda _: target)
    monkeypatch.setattr("gflow_cli.selfhost.session_health.default_profile_root", lambda: tmp_path)
    context = AsyncMock()
    access = AsyncMock(return_value=[{"private": "not-public"}])
    context.__aenter__.return_value = SimpleNamespace(list_native_media=access)
    factory = Mock(return_value=context)
    monkeypatch.setattr("gflow_cli.api.client.FlowApiClient", factory)
    return target, access, context, factory


@pytest.mark.asyncio
async def test_health_requires_actual_read_and_returns_no_timeline(probe):
    _, access, context, _ = probe
    result = await probe_project_access("fixture", P)
    assert result["health"] == "OK" and result["reason"] == "project_access_verified"
    assert result["source"] == "native-project-access" and result["checkedAt"].endswith("Z")
    assert result["profilePreserved"] is True
    assert "not-public" not in repr(result) and "fixture@example.test" not in repr(result)
    access.assert_awaited_once_with(P)
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("input_kind", ["missing_marker", "invalid_profile", "invalid_project"])
async def test_invalid_registration_never_constructs_client(probe, input_kind):
    target, _, _, factory = probe
    profile, project = "fixture", P
    if input_kind == "missing_marker":
        (target / ".gflow_account").unlink()
    elif input_kind == "invalid_profile":
        profile = "../escape"
    else:
        project = "not-uuid"
    result = await probe_project_access(profile, project)
    assert result["health"] in ("UNKNOWN", "LOGIN_REQUIRED")
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [
        (AuthMissingError(detail="private"), "LOGIN_REQUIRED"),
        (ProfileLockedError(detail="private"), "UNKNOWN"),
        (RuntimeError("private"), "UNKNOWN"),
        (TimeoutError(), "UNKNOWN"),
    ],
)
async def test_failure_projection_preserves_profile_without_raw_error(probe, error, expected):
    target, access, context, _ = probe
    access.side_effect = error
    result = await probe_project_access("fixture", P)
    assert result["health"] == expected
    assert "private" not in repr(result)
    assert (target / ".gflow_account").read_text() == "fixture@example.test"
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_identity_marker_change_cannot_report_ok(probe):
    target, access, _, _ = probe

    async def changed(project):
        (target / ".gflow_account").write_text("other@example.test")
        return []

    access.side_effect = changed
    result = await probe_project_access("fixture", P)
    assert result["health"] == "UNKNOWN" and result["reason"] == "identity_changed"


@pytest.mark.asyncio
async def test_cancel_preserves_cancellation_and_closes_client(probe):
    _, access, context, _ = probe
    access.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await probe_project_access("fixture", P)
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_health_runs_one_subprocess_and_keeps_only_safe_observation(
    tmp_path, monkeypatch
):
    import json

    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.runtime import execute
    from gflow_cli.selfhost.store import Store

    cfg = Settings(
        token="fixture", root=tmp_path, accounts={"fixture": {"email": "alias", "project": P}}
    )
    store = Store(tmp_path)
    submitted = store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    run = AsyncMock(
        return_value=(
            0,
            json.dumps(
                {
                    "status": "ok",
                    "sessionHealth": {
                        "health": "OK",
                        "reason": "project_access_verified",
                        "source": "native-project-access",
                        "checkedAt": "2026-10-03T12:00:00.000Z",
                        "profilePreserved": True,
                        "refreshAttempted": False,
                        "token": "private",
                    },
                }
            ).encode(),
        )
    )
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    assert result["sessionHealth"]["health"] == "OK" and "private" not in repr(result)
    run.assert_awaited_once()
    assert "session-health" in run.await_args.args[0]
    store.finish(submitted["jobId"], "completed", result)
    public = store.get_record(submitted["jobId"])
    assert public["response"]["sessionHealth"]["health"] == "OK"
    assert "private" not in repr(public)


def test_interrupted_read_only_health_recovers_unknown_without_submission_error(tmp_path):
    from gflow_cli.selfhost.store import Store

    store = Store(tmp_path)
    job = store.submit("accounts/health", "fixture", {"project": P}, None)
    store.claim("fixture")
    store.recover()
    record = store.get_record(job["jobId"])
    assert record["status"] == "completed"
    assert record["response"]["sessionHealth"]["health"] == "UNKNOWN"
    assert record["response"]["sessionHealth"]["reason"] == "interrupted"
    assert "error" not in record


@pytest.mark.asyncio
async def test_close_failure_is_unknown_after_successful_project_read(probe):
    _, access, context, _ = probe
    context.__aexit__.side_effect = RuntimeError("private-close-error")
    result = await probe_project_access("fixture", P)
    access.assert_awaited_once_with(P)
    assert result["health"] == "UNKNOWN" and result["reason"] == "probe_error"
    assert "private" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exit", "malformed", "timeout", "oversize"])
async def test_runtime_health_fault_is_unknown_without_resubmitting(tmp_path, monkeypatch, failure):
    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.runtime import execute
    from gflow_cli.selfhost.store import Store

    cfg = Settings(token="fixture", root=tmp_path, accounts={})
    store = Store(tmp_path)
    store.submit("accounts/health", "fixture", {"project": P}, None)
    job = store.claim("fixture")
    run = AsyncMock(
        return_value=(1, b"private-error")
        if failure == "exit"
        else (0, b"private-malformed")
        if failure == "malformed"
        else (0, b"X" * 65537)
    )
    if failure == "timeout":
        run.side_effect = TimeoutError()
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    assert result["sessionHealth"]["health"] == "UNKNOWN" and "private" not in repr(result)
    assert "error" not in result
    run.assert_awaited_once()


def test_health_is_serialized_behind_accepted_generation(tmp_path):
    from gflow_cli.selfhost.store import Store

    store = Store(tmp_path)
    first = store.submit("images", "fixture", {"project": P}, None)
    check = store.submit("accounts/health", "fixture", {"project": P}, None)
    assert store.claim("fixture")["id"] == first["jobId"]
    assert store.claim("fixture") is None
    store.finish(first["jobId"], "completed", {"media": []})
    assert store.claim("fixture")["id"] == check["jobId"]


def test_health_http_is_bound_serial_job_and_does_not_change_attestation(tmp_path):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.server import create_app

    cfg = Settings(
        token="fixture",
        root=tmp_path,
        sync_wait=0,
        accounts={"fixture": {"email": "alias", "project": P}},
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        headers = {"Authorization": "Bearer fixture", "Idempotency-Key": "health-once"}
        assert (
            client.post("/v1/google-flow/accounts/alias/health", json={"async": True}).status_code
            == 401
        )
        invalid = client.post(
            "/v1/google-flow/accounts/alias/health",
            headers=headers,
            json={"async": True, "projectId": "22222222-2222-4222-8222-222222222222"},
        )
        assert invalid.status_code == 501
        response = client.post(
            "/v1/google-flow/accounts/alias/health", headers=headers, json={"async": True}
        )
        replay = client.post(
            "/v1/google-flow/accounts/alias/health", headers=headers, json={"async": True}
        )
        assert response.status_code == replay.status_code == 201
        assert response.json()["jobId"] == replay.json()["jobId"]
        with client.app.state.store.connection() as connection:
            rows = connection.execute("SELECT * FROM jobs").fetchall()
        assert len(rows) == 1 and rows[0]["kind"] == "accounts/health"
        assert rows[0]["profile"] == "fixture"
        assert json.loads(rows[0]["payload"])["project"] == P
        assert client.app.state.store.accounts()[0]["verification_source"] == "operator-attested"
