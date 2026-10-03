import json
from unittest.mock import AsyncMock

import pytest

from gflow_cli import json_output
from gflow_cli.errors import ContentPolicyError, WafRejectionError
from gflow_cli.selfhost import native_worker, runtime
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_server import settings

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "error,code",
    [
        (WafRejectionError(detail="PUBLIC_ERROR_UNUSUAL_ACTIVITY private-path/token"), 10),
        (ContentPolicyError(detail="private prompt"), 5),
    ],
)
def test_native_worker_emits_canonical_safe_process_refusal(error, code, monkeypatch, capsys):
    monkeypatch.setattr(native_worker, "execute", AsyncMock(side_effect=error))
    monkeypatch.setattr(
        "sys.argv",
        ["native_worker", "voice-saved-create", "profile", json.dumps({"project_id": P})],
    )
    with pytest.raises(SystemExit) as caught:
        native_worker.main()
    assert caught.value.code == code
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["class"] == type(error).__name__
    assert result["error"]["exit_code"] == code
    assert result["error"]["retryable"] is False
    assert "outcome_unknown" not in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["voices/create", "videos/reference", "videos/extend", "videos/edit"]
)
@pytest.mark.parametrize(
    "error,code,expected",
    [
        (
            WafRejectionError(detail="PUBLIC_ERROR_UNUSUAL_ACTIVITY private-path/token"),
            10,
            "google_flow_unusual_activity",
        ),
        (ContentPolicyError(detail="private prompt"), 5, "google_flow_content_policy"),
    ],
)
async def test_runtime_uses_exact_typed_refusal_without_private_worker_fields(
    kind, error, code, expected, tmp_path, monkeypatch
):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    store.submit(
        kind,
        "pro1",
        {"project": P, "displayName": "Test", "voice": "Charon", "dialog": "Test"},
        None,
    )
    job = store.claim("pro1")
    envelope = json_output.error_payload(error)
    envelope["error"]["incident"] = {"path": "private filesystem path"}

    async def run(*_):
        return code, json.dumps(envelope).encode()

    monkeypatch.setattr(runtime, "subprocess_run", run)
    result = await runtime.execute(cfg, store, job)
    assert result["error"]["code"] == expected
    assert result["error"]["exit_code"] == code
    assert result["error"]["retryable"] is False
    assert "outcome_unknown" not in result["error"]
    assert "private" not in json.dumps(result)


def test_refusal_parser_rejects_spoofed_or_unknown_envelope():
    envelope = json_output.error_payload(WafRejectionError(detail="PUBLIC_ERROR_UNUSUAL_ACTIVITY"))
    assert runtime.native_refusal_error(envelope, 40) is None
    envelope["error"]["class"] = "VoiceMutationUnknownError"
    assert runtime.native_refusal_error(envelope, 10) is None


@pytest.mark.parametrize(
    "error,exit_code,expected_http,phrase",
    [
        (
            WafRejectionError(detail="PUBLIC_ERROR_UNUSUAL_ACTIVITY private"),
            10,
            403,
            "unusual activity",
        ),
        (ContentPolicyError(detail="private prompt"), 5, 400, "content policy"),
    ],
)
def test_safe_public_error_projection_names_refusal_without_unknown(
    error, exit_code, expected_http, phrase
):
    from gflow_cli.selfhost.http_jobs import error_record

    parsed = runtime.native_refusal_error(json_output.error_payload(error), exit_code)
    public = error_record({"error": parsed}, "failed")
    assert public["code"] == expected_http
    assert phrase in public["error"]
    assert public["retryable"] is False and "outcomeUnknown" not in public
    assert public["errorDetails"]["code"] == parsed["code"]
    assert "private" not in json.dumps(public)


def test_generic_waf_is_not_invented_unusual_activity():
    parsed = runtime.native_refusal_error(json_output.error_payload(WafRejectionError()), 10)
    assert parsed["code"] == "google_flow_waf_rejection"
    assert "unusual activity" not in parsed["detail"]
