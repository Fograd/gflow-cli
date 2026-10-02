from __future__ import annotations

import pytest

from gflow_cli.api.transports.migrated_projects import parse_projects

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def test_native_projects_preserves_cursor_and_drops_signed_thumbnail():
    result = parse_projects(
        [
            [
                [
                    P,
                    [
                        "My project",
                        None,
                        [1700000000, 123],
                        "https://lh3.googleusercontent.com/private",
                        M,
                    ],
                ]
            ],
            "opaque",
            "opaque",
        ]
    )
    assert result["next_cursor"] == "opaque"
    assert result["projects"] == [
        {
            "project_id": P,
            "name": "My project",
            "modified_seconds": 1700000000,
            "modified_nanos": 123,
            "last_media_id": M,
        }
    ]
    assert "private" not in repr(result)


@pytest.mark.parametrize("payload", [[], [[]]])
def test_empty_account_is_valid(payload):
    assert parse_projects(payload) == {"projects": [], "next_cursor": None}


@pytest.mark.parametrize(
    "payload", [{}, ["bad"], [[["bad", ["name"]]]], [[[P, "bad"]]], [[], {"bad": "cursor"}]]
)
def test_malformed_project_listing_fails_explicitly(payload):
    with pytest.raises(ValueError):
        parse_projects(payload)


@pytest.mark.parametrize("cursor", [None, "opaque+cursor/with=padding"])
def test_http_google_projects_preserves_native_cursor(tmp_path, monkeypatch, cursor):
    import json

    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import Settings, create_app

    calls = []

    async def run(argv, timeout):
        calls.append(argv)
        return 0, json.dumps(
            {
                "status": "ok",
                "projects": [{"project_id": P, "name": "Remote"}],
                "next_cursor": "next+opaque",
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        params = {"source": "google"}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params=params,
            headers={"Authorization": "Bearer test"},
        )
        assert response.status_code == 200
        assert response.json()["cursor"] == "next+opaque"
        assert response.json()["projects"][0]["projectId"] == P
        assert (
            "assets/projects-native"
            in client.get(
                "/v1/google-flow/capabilities", headers={"Authorization": "Bearer test"}
            ).json()["implemented"]
        )
    assert calls[0][3:5] == ["projects-list", "pro1"]
    assert json.loads(calls[0][5]) == {"cursor": cursor}


@pytest.mark.parametrize(
    "params",
    [
        {"source": "other"},
        {"source": "google", "limit": "1"},
        {"source": "google", "cursor": "x" * 4097},
    ],
)
def test_native_project_invalid_controls_do_not_launch_browser(tmp_path, monkeypatch, params):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import Settings, create_app

    async def run(*args):
        pytest.fail("Invalid native controls launched browser")

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.get(
            "/v1/google-flow/assets/projects/test@example.org",
            params=params,
            headers={"Authorization": "Bearer test"},
        )
        assert response.status_code == 422
