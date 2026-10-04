"""REST bounded resumable sync controls; no generation dispatch."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

AUTH = {"Authorization": "Bearer test-token"}
PROJECT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(
            {
                "status": "ok",
                "steps_read": 2,
                "timed_out": False,
                "traversal_finished": False,
                "complete": None,
                "observations": {"discovery": {"projects": 1}},
                "scope": "durable observed inventory; completeness unknown",
                "resource_scopes": {},
                "pending_project_count": 1,
                "catalog_projects_read": 0,
                "project_pagination_exhausted": True,
                "history_pagination_exhausted": False,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test-token",
        root=tmp_path,
        accounts={"one": {"email": "account-one", "project": PROJECT}},
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls


def test_sync_resumes_explicit_profile_with_bounded_controls(api):
    client, calls = api
    response = client.post(
        "/v1/google-flow/assets/sync/account-one",
        headers=AUTH,
        json={"maxSteps": 2, "maxSeconds": 30},
    )
    assert response.status_code == 200, response.text
    assert response.json()["complete"] is None
    argv, timeout = calls[0]
    assert argv[3:5] == ["inventory-sync", "one"]
    assert json.loads(argv[5]) == {"max_steps": 2, "max_seconds": 30, "restart": False}
    assert timeout == 75


@pytest.mark.parametrize(
    "payload",
    [
        {"maxSteps": True},
        {"maxSteps": 0},
        {"maxSteps": 101},
        {"maxSeconds": 0},
        {"maxSeconds": 301},
        {"restart": "true"},
        {"anything": 1},
    ],
)
def test_invalid_sync_controls_rejected_before_worker(api, payload):
    client, calls = api
    response = client.post("/v1/google-flow/assets/sync/account-one", headers=AUTH, json=payload)
    assert response.status_code == 422
    assert calls == []


def test_sync_unknown_account_and_missing_auth_never_dispatch(api):
    client, calls = api
    assert (
        client.post("/v1/google-flow/assets/sync/missing", headers=AUTH, json={}).status_code == 422
    )
    assert client.post("/v1/google-flow/assets/sync/account-one", json={}).status_code == 401
    assert calls == []


@pytest.mark.asyncio
async def test_account_wide_sync_worker_does_not_require_project_id(monkeypatch):
    from gflow_cli.selfhost import native_worker

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def sync(client, root, **kwargs):
        assert kwargs["profile"] == "one"
        assert kwargs["account"] == "actual@example.test"
        assert kwargs["max_steps"] == 1
        return {"steps_read": 1, "complete": None}

    monkeypatch.setattr(native_worker, "FlowApiClient", FakeClient)
    monkeypatch.setattr(
        "gflow_cli.profile_store.read_account_file", lambda _: "actual@example.test"
    )
    monkeypatch.setattr("gflow_cli.services.inventory_sync.sync_native_inventory", sync)
    result = await native_worker.execute(
        "inventory-sync", "one", {"max_steps": 1, "max_seconds": 30}
    )
    assert result["status"] == "ok" and result["steps_read"] == 1
