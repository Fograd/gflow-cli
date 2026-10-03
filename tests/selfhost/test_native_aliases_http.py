"""Composite translation is explicit, scoped and fresh; never UUID stripping."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import Settings, create_app

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
Q = "33333333-3333-4333-8333-333333333333"
ALIAS = "user:fixture-email:opaque-image:" + M
URL = "https://flow-content.google/image/owned?Signature=private"
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    state = {"kind": "image", "code": 0}

    async def run(argv, timeout):
        calls.append(argv)
        data = json.loads(argv[5])
        return state["code"], json.dumps(
            {
                "status": "ok",
                "projectId": data["project_id"],
                "mediaGenerationId": data["media_id"],
                "kind": state["kind"],
                "url": URL,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        callbacks=(),
        sync_wait=0,
        accounts={"pro1": {"email": "one", "project": P}, "pro2": {"email": "two", "project": Q}},
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls, state, tmp_path


def register(client, **values):
    return client.post(
        "/v1/google-flow/assets/one/aliases",
        headers=AUTH,
        json={"alias": ALIAS, "mediaGenerationId": M, "projectId": P, "kind": "image", **values},
    )


def read(client, alias=ALIAS, **params):
    return client.get(
        "/v1/google-flow/assets/" + quote(alias, safe=""), params=params, headers=AUTH
    )


def test_registered_alias_derives_scope_then_rechecks_fresh_media(api):
    client, calls, state, root = api
    assert register(client).status_code == 201
    assert len(calls) == 1
    response = read(client)
    assert response.status_code == 200
    assert response.json() == {"url": URL, "mediaGenerationId": ALIAS}
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 2
    assert json.loads(calls[-1][5]) == {"project_id": P, "media_id": M}
    assert b"Signature" not in (root / "aliases.sqlite3").read_bytes()


@pytest.mark.parametrize("params", [{"email": "two"}, {"projectId": Q}])
def test_alias_foreign_scope_refuses_before_google(api, params):
    client, calls, state, root = api
    assert register(client).status_code == 201
    calls.clear()
    assert read(client, **params).status_code == 403
    assert not calls


def test_unregistered_composite_never_strips_embedded_uuid(api):
    client, calls, state, root = api
    assert read(client, source="google").status_code == 404
    assert not calls


def test_wrong_native_type_cannot_be_registered(api):
    client, calls, state, root = api
    state["kind"] = "video"
    assert register(client).status_code == 400
    assert read(client, source="google").status_code == 404


@pytest.mark.parametrize(
    "values",
    [
        {"mediaGenerationId": Q},
        {"kind": "video"},
        {"alias": "user:fixture-email:opaque-image:" + M + "/bad"},
    ],
)
def test_invalid_mapping_refuses_before_lookup(api, values):
    client, calls, state, root = api
    assert register(client, **values).status_code == 422
    assert not calls


def test_identical_mapping_is_idempotent_but_conflicting_scope_is_not(api):
    client, calls, state, root = api
    assert register(client).status_code == 201
    assert register(client).status_code == 201
    assert register(client, projectId=Q).status_code == 409
    assert read(client).status_code == 200


def test_alias_fresh_lookup_failure_is_not_cached_success(api):
    client, calls, state, root = api
    assert register(client).status_code == 201
    state["code"] = 40
    response = read(client)
    assert response.status_code == 502 and "Signature" not in response.text


def test_disabled_or_unverified_mapping_refuses_before_google(api):
    client, calls, state, root = api
    assert register(client).status_code == 201
    client.app.state.store.account_set("pro1", "one", P, True, False)
    calls.clear()
    assert read(client).status_code == 403
    assert not calls


def test_alias_delete_is_local_and_scoped(api):
    client, calls, state, root = api
    assert register(client).status_code == 201
    calls.clear()
    path = "/v1/google-flow/assets/one/aliases/" + quote(ALIAS, safe="")
    response = client.delete(path, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["googleMediaDeleted"] is False
    assert not calls
    assert read(client, source="google").status_code == 404


def test_alias_registration_requires_bearer(api):
    client, calls, state, root = api
    response = client.post(
        "/v1/google-flow/assets/one/aliases",
        json={"alias": ALIAS, "mediaGenerationId": M, "kind": "image"},
    )
    assert response.status_code == 401 and not calls
