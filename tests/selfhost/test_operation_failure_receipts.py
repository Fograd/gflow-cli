"""Failure receipts retain conservative uncertainty without importing CLI diagnostics."""

import json
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.errors import NativeMediaMutationUnknownError
from gflow_cli.json_output import error_payload
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.server import create_app
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
N = "33333333-3333-4333-8333-333333333333"
AUTH = {"Authorization": "Bearer fixture"}


def settings(tmp_path):
    return Settings(
        token="fixture",
        root=tmp_path,
        accounts={"one": {"email": "alias", "project": P}},
        sync_wait=0,
    )


def payload(tmp_path, kind, mime="image/png"):
    if kind == "images":
        return {
            "project": P,
            "prompt": "test",
            "count": 1,
            "aspectRatio": "1:1",
            "model": "nano-banana-2",
        }
    path = tmp_path / ("reference.jpg" if mime == "image/jpeg" else "reference.png")
    path.write_bytes(b"fixture")
    return {"project": P, "input": str(path), "mime": mime}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,mime", [("assets", "image/png"), ("assets", "image/jpeg"), ("images", "image/png")]
)
async def test_image_upload_uncertainty_preserves_typed_reference_receipt(
    tmp_path, monkeypatch, kind, mime
):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    submitted = store.submit(kind, "one", payload(tmp_path, kind, mime), None)
    job = store.claim("one")
    envelope = error_payload(
        NativeMediaMutationUnknownError(
            operation="upload",
            phase="response",
            project_id=P,
            known_media_ids=(M,),
            pending_media_ids=(N,),
        )
    )
    envelope["error"]["detail"] = "private /cookies TOKEN"
    run = AsyncMock(return_value=(40, json.dumps(envelope).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    store.finish(submitted["jobId"], "failed", result)
    public = store.get_record(submitted["jobId"])
    assert public["outcomeUnknown"] is True
    assert public["projectId"] == P
    assert public["errorDetails"]["operation"] == "upload"
    assert public["errorDetails"]["phase"] == "response"
    if kind == "images":
        assert public["generationSubmitted"] is False
        assert public["knownReferenceMediaGenerationIds"] == [M]
        assert public["pendingReferenceMediaGenerationIds"] == [N]
        assert "knownMediaGenerationIds" not in public
    else:
        assert public["knownMediaGenerationIds"] == [M]
        assert public["pendingMediaGenerationIds"] == [N]
    assert "media" not in public.get("response", {})
    assert "private" not in repr(public) and "TOKEN" not in repr(public)
    with pytest.raises(KeyError):
        store.asset_get(M)
    run.assert_awaited_once()
    assert store.claim("one") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        b"not json /private TOKEN",
        b"x" * 65537,
        json.dumps(
            {
                "error": {
                    "class": "OtherUnknown",
                    "exit_code": 40,
                    "project_id": N,
                    "known_media_ids": [M],
                    "detail": "/private TOKEN",
                }
            }
        ).encode(),
    ],
    ids=["malformed", "oversized", "foreign-envelope"],
)
@pytest.mark.parametrize("kind", ["assets", "images"])
async def test_unrecognized_exit40_retains_trusted_scope_without_foreign_handles(
    tmp_path, monkeypatch, raw, kind
):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    submitted = store.submit(kind, "one", payload(tmp_path, kind), None)
    run = AsyncMock(return_value=(40, raw))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, store.claim("one"))
    store.finish(submitted["jobId"], "failed", result)
    public = store.get_record(submitted["jobId"])
    assert public["outcomeUnknown"] is True and public["retryable"] is False
    assert public["projectId"] == P
    assert public["errorDetails"]["code"] == "gflow_command_failed"
    assert public["errorDetails"]["exit_code"] == 40
    assert "knownMediaGenerationIds" not in public
    assert "generationSubmitted" not in public
    assert M not in repr(public) and N not in repr(public)
    assert "private" not in repr(public) and "TOKEN" not in repr(public)
    run.assert_awaited_once()
    assert store.claim("one") is None


@pytest.mark.asyncio
async def test_pre_generation_upload_refusal_is_not_unknown(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    submitted = store.submit("images", "one", payload(tmp_path, "images"), None)
    run = AsyncMock(return_value=(27, b"private upload rejection"))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, store.claim("one"))
    store.finish(submitted["jobId"], "failed", result)
    public = store.get_record(submitted["jobId"])
    assert public.get("outcomeUnknown") is not True
    assert public["retryable"] is False
    run.assert_awaited_once()


def test_legacy_generic_exit40_http_projection_remains_unknown(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        submitted = store.submit("images", "one", {"project": P, "prompt": "test"}, None)
        store.finish(
            submitted["jobId"],
            "failed",
            {
                "error": {
                    "code": "gflow_command_failed",
                    "exit_code": 40,
                    "retryable": False,
                }
            },
        )
        public = client.get("/v1/google-flow/jobs/" + submitted["jobId"], headers=AUTH).json()
        assert public["outcomeUnknown"] is True


@pytest.mark.parametrize("unknown", [False, True])
def test_failed_synchronous_upload_returns_pollable_redacted_job_receipt(
    tmp_path, monkeypatch, unknown
):
    async def fail_upload(cfg, store, job):
        return {
            "projectId": P,
            "error": {
                "code": "submission_outcome_unknown" if unknown else "gflow_command_failed",
                "exit_code": 40 if unknown else 27,
                "retryable": False,
                **({"operation": "upload", "phase": "response"} if unknown else {}),
                "detail": "private /cookies TOKEN",
            },
        }

    monkeypatch.setattr("gflow_cli.selfhost.runtime.execute", fail_upload)
    png = BytesIO()
    Image.new("RGB", (8, 8)).save(png, format="PNG")
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/v1/google-flow/assets/alias",
            headers={**AUTH, "Content-Type": "image/png"},
            content=png.getvalue(),
        )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["jobId"]
        polled = client.get("/v1/google-flow/jobs/" + detail["jobId"], headers=AUTH).json()
        assert detail["jobId"] == polled["jobId"]
        assert detail["errorDetails"] == polled["errorDetails"]
        assert detail["retryable"] is False
        assert detail.get("outcomeUnknown", False) is unknown
        assert "private" not in response.text and "TOKEN" not in response.text
        assert len(client.app.state.store.jobs()) == 1
