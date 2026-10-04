"""Resource composites bind exact fresh character/voice identities; aliases stay read-only."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

P = "11111111-1111-4111-8111-111111111111"
C = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
VW = "55555555-5555-4555-8555-555555555555"
A = "66666666-6666-4666-8666-666666666666"
Q = "77777777-7777-4777-8777-777777777777"
CHAR = "user:test-email:opaque-character:" + C + "-imgs:1"
VOICE = "user:test-email:opaque-voice:" + VW + "-mid:" + A
IMG_URL = "https://flow-content.google/image/owned?Signature=private"
AUDIO_URL = "https://flow-content.google/audio/owned?Signature=private"
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    character = {
        "entity_id": C,
        "project_id": P,
        "display_name": "Owned fixture",
        "workflow_ids": [W],
        "image_references": [{"workflow_id": W, "media_id": M, "preview_url": IMG_URL}],
        "thumbnail_media_id": Q,
        "thumbnail_url": IMG_URL,
    }
    voice = {
        "ref": A,
        "project_id": P,
        "workflow_id": VW,
        "source": "user",
        "display_name": "Owned voice",
        "audio_url": AUDIO_URL,
        "voice": A,
    }
    state = {"code": 0}

    async def run(argv, timeout):
        calls.append(argv)
        response = (
            {"status": "ok", "project_id": P, "character": character}
            if argv[3] == "character-detail"
            else {"status": "ok", **voice}
        )
        return state["code"], json.dumps(response).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "one", "project": P}, "pro2": {"email": "two", "project": Q}},
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls, character, voice, state, tmp_path


def register(client, kind="characters", alias=CHAR, **values):
    body = {"alias": alias, "projectId": P}
    body.update({"entityId": C} if kind == "characters" else {"mediaId": A, "workflowId": VW})
    body.update(values)
    return client.post("/v1/google-flow/" + kind + "/one/aliases", headers=AUTH, json=body)


def read(client, kind="characters", alias=CHAR, **params):
    return client.get(
        "/v1/google-flow/" + kind + "/" + quote(alias, safe=""), headers=AUTH, params=params
    )


@pytest.mark.parametrize("kind,alias,native", [("characters", CHAR, C), ("voices", VOICE, A)])
def test_resource_alias_register_fresh_read_local_remove(api, kind, alias, native):
    client, calls, character, voice, state, root = api
    response = register(client, kind, alias)
    assert response.status_code == 201
    assert response.json()["nativeRef"] == native
    assert response.json()["ref"] == alias
    assert response.json()["verified"] is True
    response = read(client, kind, alias)
    assert response.status_code == 200
    assert response.json()["ref"] == alias
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 2
    assert b"Signature" not in (root / "resource_aliases.sqlite3").read_bytes()
    calls.clear()
    deleted = client.delete(
        "/v1/google-flow/" + kind + "/one/aliases/" + quote(alias, safe=""), headers=AUTH
    )
    assert deleted.status_code == 200
    assert deleted.json()["googleResourceDeleted"] is False
    assert not calls
    assert read(client, kind, alias).status_code == 404
    assert not calls


def test_character_count_excludes_thumbnail(api):
    client, calls, character, voice, state, root = api
    assert register(client, alias=CHAR.replace("-imgs:1", "-imgs:2")).status_code == 400
    assert register(client).status_code == 201


def test_system_preset_cannot_satisfy_character_voice_workflow_suffix(api):
    client, calls, character, voice, state, root = api
    character["voice_detail"] = {"source": "system", "voice": "Charon"}
    assert register(client, alias=CHAR + "-voice:" + VW).status_code == 400


def test_saved_character_voice_suffix_requires_same_project_audio_and_workflow(api):
    client, calls, character, voice, state, root = api
    character["voice_detail"] = dict(voice)
    assert register(client, alias=CHAR + "-voice:" + VW).status_code == 201
    character["voice_detail"]["project_id"] = Q
    assert read(client, alias=CHAR + "-voice:" + VW).status_code == 502


@pytest.mark.parametrize("field,value", [("workflow_id", Q), ("project_id", Q), ("ref", Q)])
def test_mismatched_voice_identity_cannot_be_registered(api, field, value):
    client, calls, character, voice, state, root = api
    voice[field] = value
    assert register(client, "voices", VOICE).status_code in (400, 502)
    assert read(client, "voices", VOICE).status_code == 404


def test_orphan_voice_refuses_without_mapping(api):
    client, calls, character, voice, state, root = api
    voice["deleted"] = True
    voice.pop("audio_url")
    assert register(client, "voices", VOICE).status_code == 502
    assert read(client, "voices", VOICE).status_code == 404


@pytest.mark.parametrize("params", [{"email": "two"}, {"projectId": Q}])
def test_resource_alias_foreign_scope_refuses_before_google(api, params):
    client, calls, character, voice, state, root = api
    assert register(client).status_code == 201
    calls.clear()
    assert read(client, **params).status_code == 403
    assert not calls


def test_unknown_resource_alias_never_strips_suffix_id(api):
    client, calls, character, voice, state, root = api
    assert read(client).status_code == 404
    assert read(client, "voices", VOICE).status_code == 404
    assert not calls


def test_stale_verified_account_refuses_before_google(api):
    client, calls, character, voice, state, root = api
    assert register(client).status_code == 201
    import sqlite3

    with sqlite3.connect(root / "jobs.sqlite3") as conn:
        conn.execute("UPDATE accounts SET verified=0 WHERE profile='pro1'")
    calls.clear()
    assert read(client).status_code == 403
    assert not calls


def test_invalid_body_identity_and_foreign_removal_are_rejected(api):
    client, calls, character, voice, state, root = api
    assert register(client, entityId=Q).status_code == 422
    assert not calls
    assert register(client).status_code == 201
    calls.clear()
    result = client.delete(
        "/v1/google-flow/characters/two/aliases/" + quote(CHAR, safe=""), headers=AUTH
    )
    assert result.status_code == 403
    assert not calls
