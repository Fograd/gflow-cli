"""Default REST inventories read native history/project media; local cache is explicit."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import Settings, create_app

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        if argv[2] == "gflow_cli.cli":
            calls.append(("local-projects", None))
            return 0, b'{"projects": []}'
        query = json.loads(argv[5])
        calls.append((argv[3], query))
        if argv[3] == "history-list":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "project_summaries": [
                        {
                            "project_id": P,
                            "total": 2,
                            "by_type": {"image": 1, "video": 1},
                            "oldest": "2026-01-01T00:00:00Z",
                            "newest": "2026-01-02T00:00:00Z",
                        },
                        {
                            "project_id": Q,
                            "total": 1,
                            "by_type": {"image": 1, "video": 0},
                            "oldest": None,
                            "newest": None,
                        },
                    ],
                    "scanned": 7,
                    "truncated": True,
                    "cursor": "next-native",
                    "stopped_on": "timeBudget",
                    "complete": None,
                }
            ).encode()
        if argv[3] == "media-list":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "media": [
                        {"media_id": M, "project_id": P, "kind": "image", "likely_upload": False}
                    ],
                    "complete": None,
                }
            ).encode()
        if argv[3] == "projects-list":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "projects": [{"project_id": P, "name": "Fixture"}],
                    "next_cursor": None,
                    "complete": None,
                }
            ).encode()
        pytest.fail("Unexpected private worker dispatch")

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "one", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls


def test_default_project_inventory_is_bounded_native_history(api):
    client, calls = api
    response = client.get("/v1/google-flow/assets/projects/one", headers=AUTH)
    assert response.status_code == 200, response.text
    value = response.json()
    assert calls == [
        ("history-list", {"all_pages": True, "max_pages": 50, "max_media": 1000, "cursor": None})
    ]
    assert value["scanned"] == 7 and value["truncated"] is True
    assert value["cursor"] == "next-native" and value["stoppedOn"] == "timeBudget"
    assert value["complete"] is None
    assert value["projects"][0]["projectId"] == P
    assert value["projects"][0]["isCurrent"] is True
    assert value["projects"][0]["total"] == 2
    assert value["projects"][0]["byType"] == {"IMAGE": 1, "VIDEO": 1}
    assert value["projects"][1]["isCurrent"] is False


def test_history_continuation_is_forwarded_without_other_catalog_controls(api):
    client, calls = api
    response = client.get(
        "/v1/google-flow/assets/projects/one",
        params={"source": "history", "cursor": "opaque-resume"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert calls[0][0] == "history-list"
    assert calls[0][1]["cursor"] == "opaque-resume"
    assert calls[0][1]["all_pages"] is True


def test_explicit_local_project_inventory_never_dispatches_google(api):
    client, calls = api
    response = client.get(
        "/v1/google-flow/assets/projects/one", params={"source": "local"}, headers=AUTH
    )
    assert response.status_code == 200
    assert calls == [("local-projects", None)]


def test_explicit_google_project_catalog_route_remains_available(api):
    client, calls = api
    response = client.get(
        "/v1/google-flow/assets/projects/one", params={"source": "google"}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    assert calls[0][0] == "projects-list"


def test_default_project_media_reads_google_not_managed_cache(api):
    client, calls = api
    response = client.get("/v1/google-flow/assets/media/one", headers=AUTH)
    assert response.status_code == 200, response.text
    assert calls == [("media-list", {"project_id": P})]
    assert response.json()["media"][0]["mediaGenerationId"] == M


def test_explicit_local_media_cache_never_dispatches_google(api):
    client, calls = api
    response = client.get(
        "/v1/google-flow/assets/media/one", params={"source": "local"}, headers=AUTH
    )
    assert response.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_private_history_worker_forwards_bounded_controls_without_project(
    monkeypatch, tmp_path
):
    from gflow_cli.selfhost import native_worker

    reader = AsyncMock(return_value={"project_summaries": [], "scanned": 0, "complete": None})
    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(list_native_history=reader)
    constructor = Mock(return_value=context)
    monkeypatch.setattr(native_worker, "FlowApiClient", constructor)
    monkeypatch.setattr(
        native_worker, "get_settings", lambda: SimpleNamespace(flow_host="flow.google")
    )
    monkeypatch.setattr(native_worker.auth, "profile_dir", lambda profile: tmp_path / profile)
    result = await native_worker.execute(
        "history-list",
        "fixture",
        {
            "all_pages": True,
            "max_pages": 50,
            "max_media": 1000,
            "cursor": "opaque",
        },
    )
    reader.assert_awaited_once_with(cursor="opaque", all_pages=True, max_pages=50, max_media=1000)
    assert result["status"] == "ok"
    assert result["project_summaries"] == [] and result["complete"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "cursor-unicode",
        "cursor-control",
        "cursor-too-long",
        "completed-cursor",
        "private-date",
        "invalid-date",
        "reverse-dates",
        "half-dates",
        "duplicate-project",
    ],
)
def test_invalid_worker_summary_envelope_refuses_without_echo(api, monkeypatch, fault):
    from gflow_cli.selfhost import server

    client, calls = api
    original = server.subprocess_run

    async def corrupt(*args, **kwargs):
        code, raw = await original(*args, **kwargs)
        result = json.loads(raw)
        row = result["project_summaries"][0]
        if fault == "cursor-unicode":
            result["cursor"] = "é"
        elif fault == "cursor-control":
            result["cursor"] = "token\n"
        elif fault == "cursor-too-long":
            result["cursor"] = "x" * 4097
        elif fault == "completed-cursor":
            result["truncated"] = False
            result.pop("stopped_on", None)
        elif fault == "private-date":
            row["oldest"] = "https://flow-content.google/image/private?Signature=private"
        elif fault == "invalid-date":
            row["oldest"] = "2026-02-31T00:00:00Z"
        elif fault == "reverse-dates":
            row["oldest"], row["newest"] = row["newest"], row["oldest"]
        elif fault == "half-dates":
            row["newest"] = None
        else:
            result["project_summaries"].append(dict(row))
        return code, json.dumps(result).encode()

    monkeypatch.setattr(server, "subprocess_run", corrupt)
    response = client.get("/v1/google-flow/assets/projects/one", headers=AUTH)
    assert response.status_code == 502
    assert "Signature" not in response.text
