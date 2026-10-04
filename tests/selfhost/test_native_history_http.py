"""Measured native history controls reach the private worker; local scope refuses."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

P = "11111111-1111-4111-8111-111111111111"
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    state = {"code": 0, "include": True}
    history = {
        "workflows": [],
        "media": [],
        "counts": {"workflows": 0, "media": 0},
        "next_cursor": None,
        "pages_read": 1,
        "pagination_exhausted": True,
        "complete": None,
        "scope": "observed native account history",
    }

    async def run(argv, timeout):
        calls.append((json.loads(argv[5]), timeout))
        response = {"status": "ok", "projects": [], "next_cursor": None}
        if state["include"]:
            response["account_history"] = history
        return state["code"], json.dumps(response).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(token="test", root=tmp_path, accounts={"pro1": {"email": "one", "project": P}})
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls, state, history


def test_history_controls_roundtrip_and_unknown_completeness(api):
    client, calls, state, history = api
    response = client.get(
        "/v1/google-flow/assets/projects/one",
        headers=AUTH,
        params={
            "source": "google",
            "includeHistory": "true",
            "historyCursor": "opaque",
            "historyMaxPages": "2",
            "historyMaxMedia": "40",
        },
    )
    assert response.status_code == 200
    assert response.json()["accountHistory"] == history
    assert response.json()["complete"] is None
    assert calls[0][0] == {
        "cursor": None,
        "include_history": True,
        "history_cursor": "opaque",
        "history_max_pages": 2,
        "history_max_media": 40,
    }
    assert calls[0][1] >= 90


@pytest.mark.parametrize(
    "params",
    [
        {"includeHistory": "true"},
        {"source": "google", "includeHistory": "yes"},
        {"source": "google", "historyMaxPages": "2"},
        {"source": "google", "includeHistory": "true", "historyMaxPages": "0"},
        {"source": "google", "includeHistory": "true", "historyMaxPages": "51"},
        {"source": "google", "includeHistory": "true", "historyMaxMedia": "1001"},
        {"source": "google", "includeHistory": "true", "historyMaxMedia": "NaN"},
        {"source": "google", "includeHistory": "true", "historyCursor": ""},
        {"source": "google", "includeHistory": "true", "historyCursor": "x\n"},
    ],
)
def test_invalid_history_controls_refuse_before_worker(api, params):
    client, calls, state, history = api
    response = client.get("/v1/google-flow/assets/projects/one", headers=AUTH, params=params)
    assert response.status_code == 422
    assert not calls


def test_requested_history_must_be_returned_by_worker(api):
    client, calls, state, history = api
    state["include"] = False
    response = client.get(
        "/v1/google-flow/assets/projects/one",
        headers=AUTH,
        params={"source": "google", "includeHistory": "true"},
    )
    assert response.status_code == 502


def test_old_projects_defaults_remain_unchanged(api):
    client, calls, state, history = api
    response = client.get(
        "/v1/google-flow/assets/projects/one", headers=AUTH, params={"source": "google"}
    )
    assert response.status_code == 200
    assert "accountHistory" not in response.json()
    assert calls[0][0] == {"cursor": None}


def test_repeated_and_partial_history_reads_merge_without_deleting(api):
    client, calls, state, history = api
    workflow = "22222222-2222-4222-8222-222222222222"
    media = "33333333-3333-4333-8333-333333333333"
    history["workflows"] = [{"workflow_id": workflow, "project_id": P, "primary_media_id": media}]
    history["media"] = [
        {"media_id": media, "project_id": P, "workflow_id": workflow, "kind": "image"}
    ]
    params = {"source": "google", "includeHistory": "true"}

    def read():
        return client.get("/v1/google-flow/assets/projects/one", headers=AUTH, params=params)

    for _ in range(2):
        response = read()
        assert response.status_code == 200
        assert response.json()["inventoryObservations"]["media"] == 1
        assert response.json()["inventoryObservations"]["workflows"] == 1
        assert response.json()["inventoryObservations"]["complete"] is None
    history["workflows"] = []
    history["media"] = []
    response = read()
    assert response.status_code == 200
    assert response.json()["inventoryObservations"]["media"] == 1
    assert response.json()["inventoryObservations"]["workflows"] == 1
