"""Canonical upload causes survive queue/HTTP boundaries without raw diagnostics."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import MediaUploadRejectedError
from gflow_cli.json_output import error_payload
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
CASES = [
    ("migrated host: the upload rpc maseQ answered HTTP 400", 400, "http_error"),
    (
        "migrated host: maseQ answered 200 without a media id "
        "confirmed for the requested project id",
        200,
        "acknowledgement_unconfirmed",
    ),
    (
        "migrated host: no maseQ reply within 60s of choosing the file — "
        "the request left the page and Flow did not answer in time",
        None,
        "response_timeout_after_dispatch",
    ),
    (
        "migrated host: no maseQ reply within 60s of choosing the file — "
        "no upload request ever left the page",
        None,
        "not_dispatched",
    ),
    (
        "migrated host: a dialog opened after the file was chosen and no "
        "maseQ request left the page — most likely Flow's one-time "
        "upload-terms confirmation (host=migrated)",
        None,
        "dialog_blocked",
    ),
    ("private account@example.test /cookies token=SECRET", None, "unclassified"),
]


def envelope(detail, status=None):
    raw = error_payload(
        MediaUploadRejectedError(
            detail=detail,
            status=status,
            route="batchexecute:maseQ",
            remediation_hint="private account@example.test /cookies token=SECRET",
        )
    )
    raw["error"]["incident"] = {"path": "/private/SECRET"}
    return raw


def setup(tmp_path, kind):
    cfg = Settings(
        token="fixture", root=tmp_path, accounts={"one": {"email": "alias", "project": P}}
    )
    store = Store(tmp_path)
    if kind == "assets":
        path = tmp_path / "reference.png"
        path.write_bytes(b"fixture")
        payload = {"project": P, "mime": "image/png", "input": str(path)}
    else:
        payload = {
            "project": P,
            "prompt": "fixture",
            "model": "nano-banana-2",
            "aspectRatio": "1:1",
            "count": 1,
        }
    submitted = store.submit(kind, "one", payload, None)
    return cfg, store, submitted, store.claim("one")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail,status,reason",
    CASES,
    ids=["http", "ack", "sent-timeout", "no-dispatch", "dialog", "unknown"],
)
@pytest.mark.parametrize("kind", ["assets", "images"])
async def test_typed_upload_cause_is_safe_and_pollable(
    tmp_path, monkeypatch, detail, status, reason, kind
):
    cfg, store, submitted, job = setup(tmp_path, kind)
    run = AsyncMock(return_value=(27, json.dumps(envelope(detail, status)).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    store.finish(submitted["jobId"], "failed", result)
    receipt = store.get_record(submitted["jobId"])
    assert receipt["errorDetails"]["code"] == "gflow_command_failed"
    assert receipt["errorDetails"]["exit_code"] == 27
    assert receipt["errorDetails"]["operation"] == "upload"
    assert receipt["errorDetails"]["uploadReason"] == reason
    assert receipt["generationSubmitted"] is False
    assert receipt["retryable"] is False
    assert receipt.get("outcomeUnknown") is not True
    assert receipt["projectId"] == P
    if status is not None:
        assert receipt["errorDetails"]["nativeHttpStatus"] == status
    else:
        assert "nativeHttpStatus" not in receipt["errorDetails"]
    for value in (result, receipt):
        rendered = json.dumps(value)
        assert "SECRET" not in rendered and "/cookies" not in rendered
        assert "account@example.test" not in rendered and "remediation" not in rendered
    run.assert_awaited_once()
    assert store.claim("one") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("class", "OtherError"),
        ("type", "https://other.invalid"),
        ("exit_code", 40),
        ("exit_code", True),
    ],
)
async def test_forged_upload_error_does_not_gain_branch_metadata(
    tmp_path, monkeypatch, field, value
):
    cfg, store, submitted, job = setup(tmp_path, "assets")
    raw = envelope("migrated host: the upload rpc maseQ answered HTTP 400", 400)
    raw["error"][field] = value
    monkeypatch.setattr(
        "gflow_cli.selfhost.runtime.subprocess_run",
        AsyncMock(return_value=(27, json.dumps(raw).encode())),
    )
    result = await execute(cfg, store, job)
    store.finish(submitted["jobId"], "failed", result)
    receipt = store.get_record(submitted["jobId"])
    assert "uploadReason" not in receipt["errorDetails"]
    assert "generationSubmitted" not in receipt


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [True, "400", 0, 999])
async def test_untrusted_http_status_does_not_cross_boundary(tmp_path, monkeypatch, status):
    cfg, store, submitted, job = setup(tmp_path, "assets")
    raw = deepcopy(envelope("migrated host: the upload rpc maseQ answered HTTP 400", 400))
    raw["error"]["status"] = status
    monkeypatch.setattr(
        "gflow_cli.selfhost.runtime.subprocess_run",
        AsyncMock(return_value=(27, json.dumps(raw).encode())),
    )
    result = await execute(cfg, store, job)
    store.finish(submitted["jobId"], "failed", result)
    receipt = store.get_record(submitted["jobId"])
    assert "nativeHttpStatus" not in receipt["errorDetails"]
    assert receipt["errorDetails"]["uploadReason"] == "unclassified"


@pytest.mark.parametrize("case", CASES[:2], ids=["http", "ack"])
def test_synchronous_upload_failure_preserves_branch_in_original_job_receipt(
    tmp_path, monkeypatch, case
):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost.server import create_app

    detail, status, reason = case
    run = AsyncMock(return_value=(27, json.dumps(envelope(detail, status)).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    cfg = Settings(
        token="fixture", root=tmp_path, accounts={"one": {"email": "alias", "project": P}}
    )
    with TestClient(create_app(cfg)) as client:
        headers = {"Authorization": "Bearer fixture", "Content-Type": "image/png"}
        response = client.post(
            "/v1/google-flow/assets/alias", headers=headers, content=b"\x89PNG\r\n\x1a\nfixture"
        )
        assert response.status_code == 502
        receipt = response.json()["detail"]
        assert receipt["generationSubmitted"] is False
        assert receipt["errorDetails"]["uploadReason"] == reason
        assert receipt["errorDetails"]["nativeHttpStatus"] == status
        polled = client.get("/v1/google-flow/jobs/" + receipt["jobId"], headers=headers).json()
        assert receipt["errorDetails"] == polled["errorDetails"]
        assert "SECRET" not in response.text and "account@example.test" not in response.text
        assert len(client.app.state.store.jobs()) == 1
        run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", CASES[2:], ids=["sent-timeout", "no-dispatch", "dialog", "unknown"]
)
async def test_sdk_problem_status_is_not_mislabeled_as_native_http(tmp_path, monkeypatch, case):
    detail, _, reason = case
    cfg, store, submitted, job = setup(tmp_path, "assets")
    run = AsyncMock(return_value=(27, json.dumps(envelope(detail, 400)).encode()))
    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, job)
    store.finish(submitted["jobId"], "failed", result)
    receipt = store.get_record(submitted["jobId"])
    assert receipt["errorDetails"]["uploadReason"] == reason
    assert "nativeHttpStatus" not in result["error"]
    assert "nativeHttpStatus" not in receipt["errorDetails"]


@pytest.mark.parametrize(
    "reason",
    ["response_timeout_after_dispatch", "not_dispatched", "dialog_blocked", "unclassified"],
)
def test_http_projection_rejects_problem_status_on_other_upload_branches(reason):
    from gflow_cli.selfhost.http_jobs import error_record

    receipt = error_record(
        {
            "error": {
                "code": "gflow_command_failed",
                "exit_code": 27,
                "operation": "upload",
                "uploadReason": reason,
                "nativeHttpStatus": 400,
            }
        },
        "failed",
    )
    assert receipt["errorDetails"]["uploadReason"] == reason
    assert "nativeHttpStatus" not in receipt["errorDetails"]
