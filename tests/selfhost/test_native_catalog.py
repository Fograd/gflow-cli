from __future__ import annotations

import pytest

from gflow_cli.api.character import VOICE_NAMES
from gflow_cli.api.transports.migrated_catalog import parse_native_characters, parse_native_voices

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def test_live_system_voice_missing_from_old_enum_is_available():
    assert "Enceladus" in VOICE_NAMES


def test_native_voice_catalog_returns_canonical_name_and_public_sample():
    detail = (
        ["enceladus"]
        + [None] * 9
        + [
            [
                [
                    "Enceladus",
                    "Male, breathy, low pitch",
                    True,
                    "https://gstatic.com/aitestkitchen/voices/samples/Enceladus.wav",
                ]
            ]
        ]
    )
    payload = [None, [], [], [["enceladus", 3, "Enceladus", detail]], None, None]
    voices = parse_native_voices(payload)
    assert voices == [
        {
            "voice": "Enceladus",
            "source": "system",
            "description": "Male, breathy, low pitch",
            "sample_url": "https://gstatic.com/aitestkitchen/voices/samples/Enceladus.wav",
        }
    ]


def test_native_character_identity_and_references():
    entity = [P, E, None, [1, "Probe character", [[[W]]]], None, None, [1, 2], [3, 4]]
    payload = [None, [], [], [], None, [entity]]
    result = parse_native_characters(payload, P)
    assert result[0]["entity_id"] == E
    assert result[0]["workflow_ids"] == [W]
    assert result[0]["display_name"] == "Probe character"


def test_native_character_refuses_cross_project():
    with pytest.raises(ValueError):
        parse_native_characters([None, [], [], [], None, [[E, E, None, [1, "Other", []]]]], P)


def test_omitted_character_collection_is_empty():
    assert parse_native_characters([None, [], [], [], None, None], P) == []


@pytest.mark.parametrize(
    "kind,query,verb",
    [
        ("characters", {"email": "test@example.org", "source": "google"}, "characters-list"),
        (
            "voices",
            {"email": "test@example.org", "catalog": "google", "source": "system"},
            "voice-presets",
        ),
    ],
)
def test_native_catalog_http_routes(tmp_path, monkeypatch, kind, query, verb):
    import json

    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import Settings, create_app

    calls = []

    async def run(argv, timeout):
        calls.append(argv)
        rows = (
            [{"entity_id": E, "project_id": P, "display_name": "Test", "workflow_ids": [W]}]
            if kind == "characters"
            else [{"voice": "Enceladus", "source": "system", "description": "Low"}]
        )
        return 0, json.dumps({"status": "ok", kind: rows}).encode()

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
            "/v1/google-flow/" + kind, params=query, headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 200
        assert len(response.json()[kind]) == 1
        if kind == "characters":
            assert response.json()[kind][0]["ref"] == E
        else:
            assert response.json()[kind][0]["ref"] == "Enceladus"
    assert calls[0][3] == verb
    assert json.loads(calls[0][5]) == {"project_id": P}


def test_native_media_inventory_is_unpaginated_by_default_and_typed(tmp_path, monkeypatch):
    import json
    from uuid import UUID

    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import Settings, create_app

    rows = [
        {
            "media_id": str(UUID(int=i + 1000)),
            "project_id": P,
            "workflow_id": W,
            "kind": "image",
            "likely_upload": i % 2 == 0,
        }
        for i in range(64)
    ]
    rows[0]["created_time"] = "1970-01-01T00:00:00Z"
    rows[-1].update(kind="audio", likely_upload=False)
    rows[-2]["attached_to_project_id"] = P
    rows[-2]["project_id"] = E

    async def run(argv, timeout):
        assert argv[3] == "media-list"
        return 0, json.dumps({"status": "ok", "media": rows, "complete": None}).encode()

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
            "/v1/google-flow/assets/media/test@example.org",
            params={"source": "google"},
            headers={"Authorization": "Bearer test"},
        )
        assert response.status_code == 200
        value = response.json()
        assert len(value["media"]) == value["count"] == value["observedCount"] == 64
        assert value["likelyUploads"] == sum(row["likely_upload"] for row in rows)
        assert value["media"][0]["createTime"] == "1970-01-01T00:00:00Z"
        assert value["media"][-1]["mediaType"] == "OTHER"
        assert value["media"][-2]["projectId"] == E
        assert value["complete"] is None
        paged = client.get(
            "/v1/google-flow/assets/media/test@example.org",
            params={"source": "google", "limit": 2},
            headers={"Authorization": "Bearer test"},
        ).json()
        assert len(paged["media"]) == paged["count"] == 2
        assert paged["cursor"] and paged["observedCount"] == 64
