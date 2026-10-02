from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.selfhost.server import Settings, Store, create_app

P = "11111111-1111-4111-8111-111111111111"
E = "22222222-2222-4222-8222-222222222222"
M = "33333333-3333-4333-8333-333333333333"
M2 = "44444444-4444-4444-8444-444444444444"
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    calls = []

    async def run(argv, timeout):
        calls.append(argv)
        result = {"status": "ok", "project_id": P}
        if argv[3] == "character-delete":
            result["deleted"] = [E]
        else:
            result["character"] = {
                "entity_id": E,
                "project_id": P,
                "display_name": "Name",
                "workflow_ids": [M],
                "personality": "Calm",
            }
        if argv[3] == "characters-list":
            result["characters"] = [result.pop("character")]
        return 0, json.dumps(result).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    image = tmp_path / "known.jpg"
    Image.new("RGB", (32, 32)).save(image)
    Store(tmp_path).asset(M, "pro1", P, str(image), "image/jpeg")
    Store(tmp_path).asset(M2, "pro1", P, str(image), "image/jpeg")
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls


def test_create_maps_registered_image_before_native_worker(setup):
    client, calls = setup
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M},
    )
    assert response.status_code == 200
    assert response.json()["character"]["ref"] == E
    payload = json.loads(calls[0][5])
    assert calls[0][3] == "character-create"
    assert payload["media_id"] == M
    assert payload["image_reference_confirmed"] is True


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"displayName": "Name", "imageReference_1": E}, 422),
        ({"displayName": "", "imageReference_1": M}, 422),
        ({"displayName": "Name", "imageReference_1": M, "voice": "custom"}, 422),
        ({"displayName": "Name", "imageReference_1": M, "voice": ""}, 422),
        ({"displayName": "Name", "imageReference_1": M, "personalityNotes": "x" * 2001}, 422),
    ],
)
def test_invalid_create_never_mutates(setup, payload, status):
    client, calls = setup
    assert (
        client.post("/v1/google-flow/characters", headers=AUTH, json=payload).status_code == status
    )
    assert calls == []


def test_patch_and_delete_send_owned_entity_controls(setup):
    client, calls = setup
    assert (
        client.patch(
            "/v1/google-flow/characters/" + E, headers=AUTH, json={"personalityNotes": "Calm"}
        ).status_code
        == 200
    )
    assert json.loads(calls[0][5])["entity_id"] == E
    assert client.delete("/v1/google-flow/characters/" + E, headers=AUTH).json()["deleted"] == [E]


def test_character_detail_returns_owned_metadata(setup):
    client, calls = setup
    response = client.get("/v1/google-flow/characters/" + E.upper(), headers=AUTH)
    assert response.status_code == 200
    assert response.json()["personalityNotes"] == "Calm"
    assert response.json()["ref"] == E
    assert "sampleUrl" not in response.json()


def test_missing_character_does_not_return_other_entity(setup):
    client, calls = setup
    assert client.get("/v1/google-flow/characters/" + M, headers=AUTH).status_code == 404


def test_invalid_patch_cannot_start_mutation(setup):
    client, calls = setup
    assert (
        client.patch(
            "/v1/google-flow/characters/" + E, headers=AUTH, json={"personalityNotes": "x" * 2001}
        ).status_code
        == 422
    )
    assert client.patch("/v1/google-flow/characters/" + E, headers=AUTH, json={}).status_code == 422
    assert calls == []


def test_partial_creation_preserves_identity_without_retry(setup, monkeypatch):
    client, calls = setup

    async def partial(argv, timeout):
        calls.append(argv)
        return 0, json.dumps(
            {
                "status": "error",
                "code": "character_binding_outcome_unknown",
                "createdCharacterRef": E,
                "project_id": P,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", partial)
    response = client.patch(
        "/v1/google-flow/characters/" + E, headers=AUTH, json={"displayName": "Name"}
    )
    assert response.status_code == 502
    assert response.json()["detail"]["createdCharacterRef"] == E
    assert len(calls) == 1


def test_create_carries_valid_initial_notes_to_worker(setup):
    client, calls = setup
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M, "personalityNotes": "Calm"},
    )
    assert response.status_code == 200
    assert json.loads(calls[0][5])["personality"] == "Calm"


def test_unknown_delete_preserves_reference_without_retry(setup, monkeypatch):
    client, calls = setup

    async def partial(argv, timeout):
        calls.append(argv)
        return 0, json.dumps(
            {
                "status": "error",
                "code": "character_delete_outcome_unknown",
                "characterRef": E,
                "project_id": P,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", partial)
    response = client.delete("/v1/google-flow/characters/" + E, headers=AUTH)
    assert response.status_code == 502
    assert response.json()["detail"]["characterRef"] == E
    assert len(calls) == 1


def test_create_carries_two_registered_images_atomically(setup):
    client, calls = setup
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M, "imageReference_2": M2},
    )
    assert response.status_code == 200
    payload = json.loads(calls[0][5])
    assert payload["media_id"] == M
    assert payload["second_media_id"] == M2
    assert payload["image_reference_confirmed"] is True


def test_unknown_second_reference_never_starts_first_mutation(setup):
    client, calls = setup
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M, "imageReference_2": E},
    )
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize("invalid", ["project", "profile", "bytes", "mime"])
def test_second_image_failure_is_atomic_before_browser(setup, tmp_path, invalid):
    client, calls = setup
    store = Store(tmp_path)
    path = store.asset_get(M)["path"]
    if invalid == "bytes":
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"not image data")
        path = str(bad)
    store.asset(
        M2,
        "pro2" if invalid == "profile" else "pro1",
        E if invalid == "project" else P,
        path,
        "video/mp4" if invalid == "mime" else "image/jpeg",
    )
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M, "imageReference_2": M2},
    )
    assert response.status_code == 422
    assert calls == []


def test_create_and_update_voice_forward_literal_canonical_preset(setup):
    client, calls = setup
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Name", "imageReference_1": M, "voice": "charon"},
    )
    assert response.status_code == 200
    assert json.loads(calls[-1][-1])["voice"] == "Charon"
    response = client.patch(
        "/v1/google-flow/characters/" + E, headers=AUTH, json={"voice": "Charon"}
    )
    assert response.status_code == 200
    assert json.loads(calls[-1][-1])["voice"] == "Charon"
