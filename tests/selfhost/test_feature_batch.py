"""Feature batch routing: real job dispatch, not successful canned responses."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def test_saved_voice_create_and_delete_enqueue_native_jobs(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        created = client.post(
            "/v1/google-flow/voices",
            headers=AUTH,
            json={
                "displayName": "Narrator",
                "voice": "Charon",
                "dialog": "A small test.",
                "voicePerformance": "Warm and calm",
                "async": True,
            },
        )
        assert created.status_code == 201, created.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "voices/create"
        assert json.loads(job["payload"])["project"] == P
        deleted = client.delete("/v1/google-flow/voices/" + M + "?async=true", headers=AUTH)
        assert deleted.status_code == 201, deleted.text
        client.app.state.store.finish(created.json()["jobId"], "completed", {})
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "voices/delete"
        assert json.loads(job["payload"])["ref"] == M


def test_native_extension_explicit_or_discovered_model_queues(tmp_path):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos/extend",
            headers=AUTH,
            json={
                "mediaGenerationId": M,
                "prompt": "Continue the slow pan.",
                "modelKey": "native-extension-test-key",
                "count": 2,
                "async": True,
            },
        )
        assert response.status_code == 201, response.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "videos/extend"
        payload = json.loads(job["payload"])
        assert payload["modelKey"] == "native-extension-test-key"
        assert payload["project"] == P
        default_model = client.post(
            "/v1/google-flow/videos/extend",
            headers=AUTH,
            json={"mediaGenerationId": M, "prompt": "Continue.", "async": True},
        )
        assert default_model.status_code == 201, default_model.text
        assert len(client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"]) == 2


def test_voice_invalid_preview_does_not_enqueue(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/voices",
            headers=AUTH,
            json={
                "displayName": "Narrator",
                "voice": "Charon",
                "dialog": "x" * 121,
                "voicePerformance": "calm",
                "async": True,
            },
        )
        assert result.status_code == 422, result.text
        assert client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"] == []


def test_saved_voice_catalog_and_detail_use_native_rows(tmp_path, monkeypatch):
    from gflow_cli.selfhost import server

    row = {
        "ref": M,
        "project_id": P,
        "workflow_id": "33333333-3333-4333-8333-333333333333",
        "display_name": "Narrator",
        "dialogue": "Hello",
        "performance": "Warm",
    }

    async def worker(args, timeout):
        if args[3] == "voice-saved-get":
            return 0, json.dumps(
                {"status": "ok", **row, "audio_url": "https://example.org/audio.wav"}
            ).encode()
        assert args[3] == "voice-saved-list"
        return 0, json.dumps({"status": "ok", "voices": [row]}).encode()

    monkeypatch.setattr(server, "subprocess_run", worker)
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        listed = client.get("/v1/google-flow/voices?source=custom", headers=AUTH)
        assert listed.status_code == 200, listed.text
        assert listed.json()["voices"][0]["ref"] == M
        detail = client.get("/v1/google-flow/voices/" + M + "?source=custom", headers=AUTH)
        assert detail.status_code == 200, detail.text
        assert detail.json()["audioUrl"] == "https://example.org/audio.wav"


def test_permanent_asset_delete_queues_distinct_operation(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        result = client.request(
            "DELETE",
            "/v1/google-flow/assets/test@example.org",
            headers=AUTH,
            json={"mediaGenerationIds": [M], "projectId": P, "operation": "delete", "async": True},
        )
        assert result.status_code == 201, result.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "assets/delete"
        assert json.loads(job["payload"])["mediaGenerationIds"] == [M]


def test_video_edit_routes_omni_frame_controls_to_real_worker(tmp_path):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "model": "omni-flash",
                "modelKey": "native-edit-key",
                "referenceVideo_1": M,
                "prompt": "Replace the background with clouds.",
                "startFrameIndex_1": 0,
                "endFrameIndex_1": 48,
                "async": True,
                "referenceImage_1": "44444444-4444-4444-8444-444444444444",
                "referenceAudio_1": "55555555-5555-4555-8555-555555555555",
            },
        )
        assert response.status_code == 201, response.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "videos/edit"
        payload = json.loads(job["payload"])
        assert payload["endFrameIndex_1"] == 48
        assert payload["imageMediaIds"] == ["44444444-4444-4444-8444-444444444444"]
        assert payload["audioMediaIds"] == ["55555555-5555-4555-8555-555555555555"]
        invalid = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "model": "omni-flash",
                "modelKey": "native-edit-key",
                "referenceVideo_1": M,
                "prompt": "Continue.",
                "startFrameIndex_1": 48,
                "endFrameIndex_1": 48,
                "async": True,
            },
        )
        assert invalid.status_code == 422
        assert len(client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"]) == 1


def test_native_audio_ingredients_enqueue_reference_worker(tmp_path):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "model": "omni-flash",
                "prompt": "Let @referenceAudio_1 narrate the scene.",
                "referenceAudio_1": M,
                "count": 1,
                "aspectRatio": "1:1",
                "async": True,
            },
        )
        assert response.status_code == 201, response.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "videos/reference"
        payload = json.loads(job["payload"])
        assert payload["referenceImageIds"] == []
        assert payload["referenceAudioIds"] == [M]


def test_reference_model_catalog_forwards_audio_filter(tmp_path, monkeypatch):
    from gflow_cli.selfhost import server

    async def run(args, timeout):
        assert args[3] == "reference-models"
        assert json.loads(args[-1])["with_audio"] is True
        return 0, json.dumps({"status": "ok", "models": [{"model_key": "native-key"}]}).encode()

    monkeypatch.setattr(server, "subprocess_run", run)
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        result = client.get("/v1/google-flow/videos/reference/models?withAudio=true", headers=AUTH)
        assert result.status_code == 200, result.text
        assert result.json()["models"][0]["model_key"] == "native-key"
