"""Exact alias mutation inputs retain scoped proof and confirmed-delete receipts."""

import hashlib
import json
from urllib.parse import quote

import pytest

from gflow_cli.api.native_delete_receipts import DeleteReceipts
from gflow_cli.selfhost import server
from tests.selfhost.test_native_alias_inputs_http import (
    AUTH,
    CHARACTER,
    FOREIGN,
    IMAGE,
    IMAGE2,
    M2,
    VIDEO,
    VOICE,
    A,
    C,
    M,
    Q,
    R,
    V,
    W,
    claim,
    no_jobs,
)
from tests.selfhost.test_native_alias_inputs_http import api as base_api

api = base_api


@pytest.fixture
def mutation_api(api, monkeypatch, tmp_path):
    client, calls, state = api
    original = server.subprocess_run
    monkeypatch.setattr("gflow_cli.auth.profile_dir", lambda profile: tmp_path / profile)

    async def run(argv, timeout):
        if argv[3] not in {"character-create", "character-delete"}:
            return await original(argv, timeout)
        calls.append(argv)
        data = json.loads(argv[5])
        if argv[3] == "character-delete":
            return 0, json.dumps({"status": "ok", "deleted": [data["entity_id"]]}).encode()
        return 0, json.dumps(
            {
                "status": "ok",
                "character": {
                    "project_id": data["project_id"],
                    "entity_id": C,
                    "display_name": data["display_name"],
                    "workflow_ids": [W],
                },
            }
        ).encode()

    monkeypatch.setattr(server, "subprocess_run", run)
    return client, calls, state, tmp_path


def delete(client, route, payload=None, **params):
    return client.request(
        "DELETE", "/v1/google-flow/" + route, headers=AUTH, json=payload, params=params
    )


def receipt(root, kind="image", project=Q, owner="one@example.test"):
    profile = root / "pro1"
    profile.mkdir(exist_ok=True)
    (profile / ".gflow_account").write_text("one@example.test")
    receipts = DeleteReceipts(
        profile, hashlib.sha256(owner.casefold().encode()).hexdigest(), project
    )
    receipts.record(M, kind)


def test_asset_alias_batch_translates_in_order_and_derives_project(mutation_api):
    client, calls, _, _ = mutation_api
    response = delete(client, "assets/one", {"mediaGenerationIds": [VIDEO, IMAGE], "async": True})
    assert response.status_code == 201, response.text
    payload = claim(client)
    assert payload["mediaGenerationIds"] == [V, M]
    assert payload["projectId"] == Q
    assert [argv[3] for argv in calls] == ["asset-get", "asset-get"]


def test_asset_confirmed_receipt_skips_unavailable_fresh_get(mutation_api):
    client, calls, state, root = mutation_api
    receipt(root)
    state["stale"] = True
    response = delete(
        client, "assets/one", {"mediaGenerationIds": [IMAGE], "operation": "delete", "async": True}
    )
    assert response.status_code == 201, response.text
    assert claim(client)["mediaGenerationIds"] == [M]
    assert calls == []


@pytest.mark.parametrize("fault", ["absent", "kind", "project", "owner", "archive"])
def test_absence_or_unrelated_receipt_does_not_adopt_deleted_alias(mutation_api, fault):
    client, calls, state, root = mutation_api
    if fault != "absent":
        receipt(
            root,
            kind="video" if fault == "kind" else "image",
            project=R if fault == "project" else Q,
            owner="two@example.test" if fault == "owner" else "one@example.test",
        )
    state["stale"] = True
    response = delete(
        client,
        "assets/one",
        {
            "mediaGenerationIds": [IMAGE],
            "operation": "archive" if fault == "archive" else "delete",
            "async": True,
        },
    )
    assert response.status_code == 502, response.text
    assert [argv[3] for argv in calls] == ["asset-get"]
    no_jobs(client)


@pytest.mark.parametrize(
    "values,account,project,status",
    [
        ([IMAGE, FOREIGN], "one", None, 409),
        ([IMAGE], "two", None, 403),
        ([IMAGE], "one", R, 403),
        ([CHARACTER], "one", None, 400),
    ],
)
def test_asset_alias_scope_and_duplicate_guards(mutation_api, values, account, project, status):
    client, calls, _, _ = mutation_api
    payload = {"mediaGenerationIds": values, "async": True}
    if project:
        payload["projectId"] = project
    response = delete(client, "assets/" + account, payload)
    assert response.status_code == status, response.text
    no_jobs(client)
    if status != 422:
        assert calls == []


def test_permanent_alias_and_uuid_duplicates_normalize_after_exact_mapping(mutation_api):
    client, calls, _, _ = mutation_api
    response = delete(
        client,
        "assets/one",
        {
            "mediaGenerationIds": [IMAGE, M.upper(), VIDEO, IMAGE, V],
            "operation": "delete",
            "async": True,
        },
    )
    assert response.status_code == 201, response.text
    assert claim(client)["mediaGenerationIds"] == [M, V]
    assert [argv[3] for argv in calls] == ["asset-get", "asset-get"]


def test_archive_still_refuses_alias_and_uuid_duplicates(mutation_api):
    client, _, _, _ = mutation_api
    response = delete(client, "assets/one", {"mediaGenerationIds": [IMAGE, M], "async": True})
    assert response.status_code == 422
    no_jobs(client)


@pytest.mark.parametrize("count,status", [(0, 422), (1, 201), (100, 201), (101, 422)])
def test_delete_distinct_boundaries_and_repeated_ids(mutation_api, count, status):
    from uuid import UUID

    client, _, _, _ = mutation_api
    identifiers = [str(UUID(int=i + 1)) for i in range(count)]
    response = delete(
        client,
        "assets/one",
        {
            "mediaGenerationIds": identifiers + identifiers,
            "operation": "delete",
            "async": True,
        },
    )
    assert response.status_code == status, response.text
    if status == 201:
        assert claim(client)["mediaGenerationIds"] == identifiers
    else:
        no_jobs(client)


def test_delete_character_and_saved_voice_aliases(mutation_api):
    client, calls, _, _ = mutation_api
    character = delete(client, "characters/" + quote(CHARACTER, safe=""))
    assert character.status_code == 200, character.text
    assert character.json()["deleted"] == [C]
    assert json.loads(calls[1][5]) == {"project_id": Q, "entity_id": C}
    voice = delete(client, "voices/" + quote(VOICE, safe=""), **{"async": "true"})
    assert voice.status_code == 201, voice.text
    payload = claim(client)
    assert payload["ref"] == A and payload["projectId"] == Q
    assert [argv[3] for argv in calls] == [
        "character-detail",
        "character-delete",
        "voice-saved-get",
    ]


def test_create_character_alias_images_and_owned_voice(mutation_api):
    client, calls, _, _ = mutation_api
    client.app.state.store.asset_delete(M2)
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={
            "displayName": "Hero",
            "imageReference_1": IMAGE,
            "imageReference_2": IMAGE2,
            "voice": VOICE,
        },
    )
    assert response.status_code == 200, response.text
    data = json.loads(calls[-1][5])
    assert data["project_id"] == Q
    assert data["media_id"] == M and data["second_media_id"] == M2
    assert data["voice"] == A and data["image_reference_confirmed"] is True
    assert [argv[3] for argv in calls] == [
        "asset-get",
        "asset-get",
        "voice-saved-get",
        "asset-cache-image",
        "character-create",
    ]


@pytest.mark.parametrize("operation", ["character-delete", "voice-delete", "character-create"])
def test_stale_alias_refuses_all_resource_mutations(mutation_api, operation):
    client, calls, state, _ = mutation_api
    state["stale"] = True
    if operation == "character-create":
        response = client.post(
            "/v1/google-flow/characters",
            headers=AUTH,
            json={"displayName": "Hero", "imageReference_1": IMAGE, "voice": VOICE},
        )
    else:
        alias = CHARACTER if operation == "character-delete" else VOICE
        route = "characters/" if operation == "character-delete" else "voices/"
        response = delete(
            client,
            route + quote(alias, safe=""),
            **({"async": "true"} if operation == "voice-delete" else {}),
        )
    assert response.status_code == 502, response.text
    assert all(argv[3] not in {"character-delete", "character-create"} for argv in calls)
    no_jobs(client)


def test_malformed_receipt_fails_before_fresh_read_or_queue(mutation_api):
    client, calls, _, root = mutation_api
    receipt(root)
    owner = hashlib.sha256(b"one@example.test").hexdigest()
    path = root / "pro1" / ".gflow_delete_receipts" / owner / Q / (M + ".json")
    path.write_text("{}")
    response = delete(
        client, "assets/one", {"mediaGenerationIds": [IMAGE], "operation": "delete", "async": True}
    )
    assert response.status_code == 409, response.text
    assert calls == []
    no_jobs(client)


@pytest.mark.parametrize("route,alias", [("characters/", CHARACTER), ("voices/", VOICE)])
@pytest.mark.parametrize("params,status", [({"email": "two"}, 403), ({"projectId": R}, 403)])
def test_resource_delete_scope_fails_without_lookup(mutation_api, route, alias, params, status):
    client, calls, _, _ = mutation_api
    response = delete(client, route + quote(alias, safe=""), **params)
    assert response.status_code == status, response.text
    assert calls == []
    no_jobs(client)


def test_create_character_mixed_alias_scope_fails_without_lookup(mutation_api):
    client, calls, _, _ = mutation_api
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Hero", "imageReference_1": FOREIGN, "voice": VOICE},
    )
    assert response.status_code == 409, response.text
    assert calls == []


@pytest.mark.parametrize("route", ["characters/", "voices/"])
def test_missing_exact_resource_alias_mapping_is_not_parsed_as_owned(mutation_api, route):
    client, calls, _, _ = mutation_api
    alias = (CHARACTER if route == "characters/" else VOICE).replace("opaque", "unmapped")
    response = delete(client, route + quote(alias, safe=""))
    assert response.status_code == 404, response.text
    assert calls == []
    no_jobs(client)


def test_create_character_voice_workflow_declaration_must_be_fresh(mutation_api, monkeypatch):
    client, calls, _, _ = mutation_api
    original = server.subprocess_run

    async def run(argv, timeout):
        code, raw = await original(argv, timeout)
        if argv[3] == "voice-saved-get":
            data = json.loads(raw)
            data["workflow_id"] = W
            raw = json.dumps(data).encode()
        return code, raw

    monkeypatch.setattr(server, "subprocess_run", run)
    response = client.post(
        "/v1/google-flow/characters",
        headers=AUTH,
        json={"displayName": "Hero", "imageReference_1": IMAGE, "voice": VOICE},
    )
    assert response.status_code == 502, response.text
    assert [argv[3] for argv in calls] == ["asset-get", "voice-saved-get"]


@pytest.mark.parametrize("marker", [None, "other@example.test", "not-an-email"])
def test_receipt_requires_current_verified_google_marker(mutation_api, marker):
    client, calls, state, root = mutation_api
    receipt(root)
    path = root / "pro1" / ".gflow_account"
    if marker is None:
        path.unlink()
    else:
        path.write_text(marker)
    state["stale"] = True
    response = delete(
        client, "assets/one", {"mediaGenerationIds": [IMAGE], "operation": "delete", "async": True}
    )
    assert response.status_code == 502, response.text
    assert [argv[3] for argv in calls] == ["asset-get"]
    no_jobs(client)
