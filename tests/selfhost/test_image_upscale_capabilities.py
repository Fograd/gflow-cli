"""Synchronous image capability reads cannot create paid jobs or leak worker metadata."""

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings
from tests.services.test_image_upscale_capability_mirrors import RESULT, M, P


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    answer = [{"status": "ok", **deepcopy(RESULT)}]

    async def run(argv, timeout):
        calls.append((argv, timeout))
        return 0, json.dumps(answer[0]).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        yield client, calls, answer


PATH = "/v1/google-flow/images/upscale/capabilities"


def test_http_selects_exact_owned_image_sync_no_jobs(api):
    client, calls, _ = api
    response = client.get(
        PATH,
        headers=AUTH,
        params={"email": "test@example.org", "projectId": P, "mediaGenerationId": M},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "projectId": P,
        "mediaGenerationId": M,
        "capabilities": RESULT["capabilities"],
        "scope": RESULT["scope"],
    }
    argv, timeout = calls[0]
    assert argv[3:5] == ["image-upscale-capabilities", "pro1"]
    assert json.loads(argv[5]) == {"project_id": P, "media_id": M}
    assert timeout == 60
    assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []


@pytest.mark.parametrize(
    "params,status",
    [
        ({}, 422),
        ({"mediaGenerationId": "bad"}, 422),
        ({"mediaGenerationId": M, "projectId": "bad"}, 422),
        ({"mediaGenerationId": M, "async": "true"}, 501),
        ({"mediaGenerationId": M, "resolution": "4k"}, 501),
    ],
)
def test_invalid_controls_never_dispatch(api, params, status):
    client, calls, _ = api
    assert client.get(PATH, headers=AUTH, params=params).status_code == status
    assert calls == []


def test_auth_and_duplicate_query_refuse_before_worker(api):
    client, calls, _ = api
    assert client.get(PATH, params={"mediaGenerationId": M}).status_code == 401
    assert (
        client.get(
            PATH + "?mediaGenerationId=" + M + "&mediaGenerationId=" + M, headers=AUTH
        ).status_code
        == 501
    )
    assert calls == []


@pytest.mark.parametrize(
    "patch",
    [
        {"media_id": P},
        {"project_id": M},
        {"scope": "account-wide entitlement"},
        {"capabilities": []},
        {
            "capabilities": [
                {
                    "resolution": "2k",
                    "status": "unknown",
                    "available": False,
                    "reason": "observation_timeout",
                },
                RESULT["capabilities"][1],
            ]
        },
        {
            "capabilities": [
                {**RESULT["capabilities"][0], "url": "https://secret.invalid"},
                RESULT["capabilities"][1],
            ]
        },
    ],
)
def test_inconsistent_or_secret_worker_result_never_publishes(api, patch):
    client, _, answer = api
    answer[0].update(patch)
    response = client.get(PATH, headers=AUTH, params={"mediaGenerationId": M})
    assert response.status_code == 502
    assert "secret" not in response.text


@pytest.mark.parametrize("field,value", [("status", []), ("reason", {}), ("available", 1)])
def test_unhashable_or_nonboolean_worker_fields_are_rejected(api, field, value):
    client, _, answer = api
    answer[0]["capabilities"][0][field] = value
    response = client.get(PATH, headers=AUTH, params={"mediaGenerationId": M})
    assert response.status_code == 502
