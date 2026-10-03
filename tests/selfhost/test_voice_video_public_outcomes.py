import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli import json_output
from gflow_cli.errors import NativeVideoGenerationUnknownError, VoiceMutationUnknownError
from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_http_jobs import AUTH, PROJECT, cfg

M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


def body(voice=True):
    common = {"async": True, "replyUrl": "https://callbacks.example/hook", "replyRef": "caller"}
    return (
        {
            **common,
            "displayName": "Test voice",
            "voice": "Charon",
            "dialog": "Hello",
            "performance": "Calm",
        }
        if voice
        else {
            **common,
            "model": "omni-flash",
            "modelKey": "native",
            "referenceImage_1": M,
            "prompt": "Animate",
        }
    )


def run_and_project(client, monkeypatch, payload, worker_result, exit_code, state, route):
    headers = {**AUTH, "Idempotency-Key": "same"}
    accepted = client.post(route, headers=headers, json=payload)
    assert accepted.status_code == 201, accepted.text
    store = client.app.state.store
    job = store.claim("pro1")

    async def fake_run(*_):
        return exit_code, json.dumps(worker_result).encode()

    monkeypatch.setattr(runtime, "subprocess_run", fake_run)
    result = asyncio.run(runtime.execute(client.app.state.cfg, store, job))
    store.finish(job["id"], state, result)
    record = client.get("/v1/google-flow/jobs/" + job["id"], headers=AUTH).json()
    with store.connection() as conn:
        callback = json.loads(
            conn.execute(
                "SELECT payload FROM callbacks WHERE job=? AND state=?", (job["id"], state)
            ).fetchone()[0]
        )
    assert callback == record
    synchronous = client.post(route, headers=headers, json={**payload, "async": False})
    return record, synchronous


def test_acknowledged_tts_handles_survive_get_sync_and_callback(tmp_path, monkeypatch):
    configuration = cfg(tmp_path)
    with TestClient(create_app(configuration, start_workers=False)) as client:
        client.app.state.cfg = configuration
        result = {
            "status": "ok",
            "ref": M,
            "workflow_id": W,
            "display_name": "Test voice",
            "preset_voice": "charon",
            "dialogue": "Hello",
            "performance": "Calm",
            "internalPath": "/private/token",
        }
        record, sync = run_and_project(
            client, monkeypatch, body(), result, 0, "completed", "/v1/google-flow/voices"
        )
        for public in (record, record["response"], sync.json()):
            assert public["ref"] == public["mediaId"] == public["voice"] == M
            assert public["workflowId"] == W and public["source"] == "user"
            assert public["displayName"] == "Test voice" and public["baseVoice"] == "charon"
            assert public["dialog"] == "Hello" and public["voicePerformance"] == "Calm"
            assert "/private/token" not in json.dumps(public)
        assert sync.status_code == 200


@pytest.mark.parametrize("voice", [True, False])
def test_unknown_native_handles_survive_get_sync_and_callback(voice, tmp_path, monkeypatch):
    error = (
        VoiceMutationUnknownError(project_id=PROJECT, phase="save", media_id=M, workflow_id=W)
        if voice
        else NativeVideoGenerationUnknownError(
            project_id=PROJECT, media_ids=(M,), workflow_ids=(W,), phase="video_submit"
        )
    )
    envelope = json_output.error_payload(error)
    envelope["error"]["internalPath"] = "/private/token"
    configuration = cfg(tmp_path)
    with TestClient(create_app(configuration, start_workers=False)) as client:
        client.app.state.cfg = configuration
        record, sync = run_and_project(
            client,
            monkeypatch,
            body(voice),
            envelope,
            40,
            "failed",
            "/v1/google-flow/voices" if voice else "/v1/google-flow/videos",
        )
        for public in (record, sync.json()):
            assert public["outcomeUnknown"] is True and public["retryable"] is False
            assert public["knownMediaGenerationIds"] == [M]
            assert public["knownWorkflowIds"] == [W]
            assert public["errorDetails"]["phase"] == ("save" if voice else "video_submit")
            assert "/private/token" not in json.dumps(public)
        assert sync.status_code == 502


def test_voice_shape_and_unknown_vectors_do_not_accept_private_invalid_values():
    from gflow_cli.selfhost.http_jobs import error_record, result_record

    valid = {
        "projectId": PROJECT,
        "ref": M,
        "mediaId": M,
        "voice": M,
        "workflowId": W,
        "source": "user",
        "displayName": "Test",
    }
    assert "ref" not in result_record(valid, kind="images")
    assert "ref" not in result_record(
        {**valid, "voice": "https://secret/voice"}, kind="voices/create"
    )
    assert "dialog" not in result_record({**valid, "dialog": "x" * 10000}, kind="voices/create")
    unknown = {
        "projectId": PROJECT,
        "error": {
            "code": "native_video_generation_outcome_unknown",
            "outcome_unknown": True,
            "media_ids": [M, "/private/token"],
            "workflow_ids": [W],
            "phase": "untrusted",
        },
    }
    public = error_record(unknown, "failed")
    assert public["outcomeUnknown"] is True
    assert "media_ids" not in public["errorDetails"] and "phase" not in public["errorDetails"]
    assert "/private/token" not in json.dumps(public)
    assert "outcomeUnknown" not in error_record(
        {"error": {"code": "arbitrary", "outcome_unknown": True}}, "failed"
    )


@pytest.mark.parametrize("raw_code", [None, [], {}, True, "arbitrary"])
def test_untyped_error_codes_cannot_create_native_recovery_fields(raw_code):
    from gflow_cli.selfhost.http_jobs import result_record

    result = {
        "projectId": PROJECT,
        "error": {"code": raw_code, "outcome_unknown": True, "media_ids": [M], "workflow_ids": [W]},
    }
    assert "knownMediaGenerationIds" not in result_record(result)


@pytest.mark.parametrize(
    "code", ["native_video_edit_outcome_unknown", "native_video_extension_outcome_unknown"]
)
def test_each_native_video_unknown_code_preserves_validated_recovery(code):
    from gflow_cli.selfhost.http_jobs import error_record

    result = {
        "projectId": PROJECT,
        "error": {
            "code": code,
            "outcome_unknown": True,
            "media_ids": [M],
            "workflow_ids": [W],
            "phase": "video_poll",
        },
    }
    public = error_record(result, "failed")
    assert public["outcomeUnknown"] is True
    assert public["knownMediaGenerationIds"] == [M]
    assert public["knownWorkflowIds"] == [W]
    assert public["errorDetails"]["phase"] == "video_poll"
