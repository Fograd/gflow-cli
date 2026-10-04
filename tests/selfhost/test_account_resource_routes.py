"""REST traversal limits, continuation and safe resource envelope projection."""

import hashlib
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

P = "11111111-1111-4111-8111-111111111111"
R = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def envelope(kind="character"):
    return {
        "status": "ok",
        "kind": kind,
        "resources": [
            {
                "kind": kind,
                "native_id": R,
                "origin_project_id": P,
                "observed_in_project_ids": [P],
                **({"workflow_ids": [W]} if kind == "character" else {"workflow_id": W}),
                "url": "https://private.example/secret",
                "display_name": "private name",
            }
        ],
        "returned_count": 1,
        "observed_count": 1,
        "next_cursor": "a" * 32,
        "pending_result_count": 0,
        "pending_project_count": 1,
        "pages_read": 1,
        "catalog_projects_read": 1,
        "total_pages_read": 1,
        "total_catalog_projects_read": 1,
        "cursor_count": 0,
        "project_pagination_exhausted": True,
        "traversal_finished": False,
        "timed_out": False,
        "truncated": True,
        "complete": None,
        "deletion_authority": False,
        "scope": "observed account project catalogs; completeness unknown",
        "private": "secret",
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    answer = [envelope()]

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(answer[0]).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    monkeypatch.setattr(
        "gflow_cli.selfhost.account_marker.read_verified_account",
        lambda _: "actual-private@example.test",
    )
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        yield client, calls, answer


@pytest.mark.parametrize("kind", ["character", "voice"])
def test_resources_dispatch_bounded_read_and_remove_private_fields(api, kind):
    client, calls, answer = api
    answer[0] = envelope(kind)
    response = client.get(
        "/v1/google-flow/assets/resources/test@example.org",
        headers=AUTH,
        params={"kind": kind, "maxProjects": 2, "maxPages": 3, "maxSeconds": 30},
    )
    assert response.status_code == 200, response.text
    assert "private" not in response.text and "display_name" not in response.text
    assert response.json()["complete"] is None and response.json()["deletion_authority"] is False
    argv, timeout = calls[0]
    assert argv[3:5] == ["account-resources", "pro1"]
    assert json.loads(argv[5]) == {
        "kind": kind,
        "cursor": None,
        "max_projects": 2,
        "max_pages": 3,
        "max_seconds": 30,
        "expected_account_sha256": hashlib.sha256(b"actual-private@example.test").hexdigest(),
    }
    assert timeout == 75


@pytest.mark.parametrize(
    "params",
    [
        {"kind": "audio"},
        {"cursor": ""},
        {"cursor": "raw-google-cursor"},
        {"maxProjects": "0"},
        {"maxProjects": "21"},
        {"maxPages": "101"},
        {"maxSeconds": "181"},
        {"maxSeconds": "true"},
        {"maxPages": "1.5"},
    ],
)
def test_invalid_read_controls_never_dispatch(api, params):
    client, calls, _ = api
    response = client.get(
        "/v1/google-flow/assets/resources/test@example.org", headers=AUTH, params=params
    )
    assert response.status_code == 422, response.text
    assert calls == []


def test_resources_reject_unknown_query_duplicate_and_auth(api):
    client, calls, _ = api
    route = "/v1/google-flow/assets/resources/test@example.org"
    assert client.get(route).status_code == 401
    assert client.get(route + "?kind=voice&kind=character", headers=AUTH).status_code == 501
    assert client.get(route + "?projectId=" + P, headers=AUTH).status_code == 501
    assert calls == []


@pytest.mark.parametrize(
    "patch",
    [
        {"complete": True},
        {"deletion_authority": True},
        {"pages_read": True},
        {"pages_read": 2},
        {"returned_count": 2},
        {"next_cursor": "nativeGoogleCursor"},
        {"truncated": False},
        {"pending_project_count": -1},
        {"kind": "voice"},
        {"scope": "authoritative"},
        {
            "resources": [
                {
                    "kind": "character",
                    "native_id": R,
                    "origin_project_id": P,
                    "observed_in_project_ids": [W],
                    "workflow_ids": [],
                }
            ]
        },
    ],
)
def test_malformed_worker_does_not_publish(api, patch):
    client, _, answer = api
    answer[0] = {**deepcopy(envelope()), **patch}
    response = client.get("/v1/google-flow/assets/resources/test@example.org", headers=AUTH)
    assert response.status_code == 502, response.text
    assert "secret" not in response.text


def test_changed_private_principal_is_not_published(api, monkeypatch):
    client, _, _ = api
    identities = iter(["actual-private@example.test", "other@example.test"])
    monkeypatch.setattr(
        "gflow_cli.selfhost.account_marker.read_verified_account", lambda _: next(identities)
    )
    response = client.get("/v1/google-flow/assets/resources/test@example.org", headers=AUTH)
    assert response.status_code == 409
    assert "actual-private" not in response.text and "other@" not in response.text


def test_missing_private_principal_refuses_before_worker(api, monkeypatch):
    client, calls, _ = api
    monkeypatch.setattr("gflow_cli.selfhost.account_marker.read_verified_account", lambda _: None)
    response = client.get("/v1/google-flow/assets/resources/test@example.org", headers=AUTH)
    assert response.status_code == 409
    assert calls == []
