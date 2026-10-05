"""R11 adapter contracts use controlled queues; no Google mutation is dispatched."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_http_jobs import AUTH, PROJECT, cfg
from tests.selfhost.test_native_captcha_controls import request


@pytest.mark.parametrize("kind", ["voices/create", "videos/edit", "videos/reference"])
def test_accepted_native_request_fields_survive_polling_and_callbacks(tmp_path, kind):
    endpoint, body = request(kind)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "async": True, "replyUrl": "https://callbacks.example/hook"},
        )
        assert response.status_code == 201, response.text
        expected = {**body}
        public = response.json()
        assert expected.items() <= public["request"].items()
        identifier = public["jobId"]
        assert client.get(response.headers["location"], headers=AUTH).json() == public
        with client.app.state.store.connection() as connection:
            callback = json.loads(
                connection.execute(
                    "SELECT payload FROM callbacks WHERE job=?", (identifier,)
                ).fetchone()[0]
            )
        assert callback == public


@pytest.mark.parametrize("alias,canonical", [("landscape", "16:9"), ("portrait", "9:16")])
@pytest.mark.parametrize("kind", ["videos/extend", "videos/reference"])
def test_native_video_aspect_aliases_reach_worker_payload(tmp_path, alias, canonical, kind):
    endpoint, body = request(kind)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "async": True, "aspectRatio": alias},
        )
        assert response.status_code == 201, response.text
        payload = json.loads(client.app.state.store.claim("pro1")["payload"])
        assert payload["aspectRatio"] == canonical
        assert response.json()["request"]["aspectRatio"] == canonical


def test_native_reference_4k_spelling_reaches_existing_resolution_control(tmp_path):
    endpoint, body = request("videos/reference")
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "resolution": "4K", "async": True},
        )
        assert response.status_code == 201, response.text
        assert json.loads(client.app.state.store.claim("pro1")["payload"])["resolution"] == "4k"


@pytest.mark.parametrize("value", [None, "", False, 0, [], {}])
@pytest.mark.parametrize("kind", ["videos/extend", "videos/reference"])
def test_explicit_invalid_native_model_key_never_defaults_or_enqueues(tmp_path, kind, value):
    endpoint, body = request(kind)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "async": True, "modelKey": value},
        )
        assert response.status_code == 422, response.text
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("value", [None, "", False, 0, [], {}])
@pytest.mark.parametrize("kind", ["videos/edit", "videos/reference"])
def test_supplied_invalid_native_reference_never_disappears(tmp_path, kind, value):
    endpoint, body = request(kind)
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "async": True, "referenceAudio_1": value},
        )
        assert response.status_code == 422, response.text
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("value", [None, "", False, 0, [], {}])
@pytest.mark.parametrize("endpoint", ["/images", "/videos"])
def test_explicit_invalid_project_never_falls_back_or_enqueues(tmp_path, endpoint, value):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={"prompt": "x", "async": True, "projectId": value},
        )
        assert response.status_code == 422, response.text
        assert client.app.state.store.jobs() == []


def test_voice_performance_extension_projects_canonical_public_name(tmp_path):
    endpoint, body = request("voices/create")
    body["performance"] = body.pop("voicePerformance")
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint, headers=AUTH, json={**body, "async": True}
        )
        assert response.status_code == 201
        assert response.json()["request"]["voicePerformance"] == "Calm"
        assert "performance" not in response.json()["request"]


def test_added_projection_fields_never_echo_private_controls():
    from gflow_cli.selfhost.http_jobs import request_record

    value = request_record(
        dict(
            referenceAudio_1="Charon",
            referenceVideo_1=PROJECT,
            startFrameIndex_1=0,
            endFrameIndex_1=24,
            trimStartFrame=0,
            trimEndFrame=48,
            captchaToken="private-token",
            captchaSecret="/private/token",
            referenceSlotIds={"secret": "private"},
            privateUrl="https://signed/?secret",
        )
    )
    assert value == dict(
        referenceAudio_1="Charon",
        referenceVideo_1=PROJECT,
        startFrameIndex_1=0,
        endFrameIndex_1=24,
        trimStartFrame=0,
        trimEndFrame=48,
    )


@pytest.mark.parametrize("value", [None, "", False, 0, [], {}])
@pytest.mark.parametrize(
    "endpoint,mime", [("/images/upscale", "image/png"), ("/videos/upscale", "video/mp4")]
)
def test_managed_upscale_never_overwrites_invalid_explicit_project(tmp_path, endpoint, mime, value):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        client.app.state.store.asset(PROJECT, "pro1", PROJECT, str(tmp_path / "fixture"), mime)
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={"mediaGenerationId": PROJECT, "projectId": value, "async": True},
        )
        assert response.status_code == 422, response.text
        assert client.app.state.store.jobs() == []


def test_extension_text_form_trims_reach_worker_as_integers(tmp_path):
    endpoint, body = request("videos/extend")
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            files={
                key: (None, str(value))
                for key, value in {
                    **body,
                    "async": "true",
                    "trimStartFrame": 0,
                    "trimEndFrame": 24,
                }.items()
            },
        )
        assert response.status_code == 201, response.text
        payload = json.loads(client.app.state.store.claim("pro1")["payload"])
        assert type(payload["trimStartFrame"]) is int and payload["trimStartFrame"] == 0
        assert type(payload["trimEndFrame"]) is int and payload["trimEndFrame"] == 24


@pytest.mark.parametrize(
    "model", [None, "veo-3.1-fast", "veo-3.1-quality", "veo-3.1-lite", "veo-3.1-lite-low-priority"]
)
def test_http_extension_model_default_and_alias_reach_private_worker(tmp_path, model):
    endpoint, body = request("videos/extend")
    body.pop("modelKey")
    if model is not None:
        body["model"] = model
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint, headers=AUTH, json={**body, "async": True}
        )
        assert response.status_code == 201, response.text
        payload = json.loads(client.app.state.store.claim("pro1")["payload"])
        assert payload["model"] == (model or "veo-3.1-fast")
        assert response.json()["request"]["model"] == payload["model"]


@pytest.mark.parametrize("model", ["omni-flash", "unknown", False, None, []])
def test_invalid_extension_model_never_enqueues(tmp_path, model):
    endpoint, body = request("videos/extend")
    body.pop("modelKey")
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "model": model, "async": True},
        )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []


def test_extension_model_and_exact_native_key_conflict_never_enqueues(tmp_path):
    endpoint, body = request("videos/extend")
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "model": "veo-3.1-fast", "async": True},
        )
        assert response.status_code == 422
        assert client.app.state.store.jobs() == []
