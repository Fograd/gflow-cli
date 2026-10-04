"""Safe typed quota HTTP projection and public statistics history."""

import pytest

from gflow_cli.selfhost.http_jobs import error_record, http_status
from gflow_cli.selfhost.job_statistics import statistics
from tests.selfhost.test_model_quarantine import DAILY, KEY, refusal
from tests.selfhost.test_model_quarantine import env as env


@pytest.mark.parametrize(
    "reason,status",
    [
        (DAILY, 429),
        ("PUBLIC_ERROR_MODEL_ACCESS_DENIED", 403),
    ],
)
def test_positive_quota_http_and_history_are_safe(env, reason, status):
    store, cfg, now = env
    result = refusal(reason)
    result["error"]["detail"] = "private-cookie; captcha-token; /private/profile"
    assert http_status(result, "failed") == status
    safe = error_record(result, "failed")
    assert safe["code"] == status
    assert safe["errorDetails"]["nativeReason"] == reason
    assert safe["errorDetails"]["nativeModelKey"] == KEY
    assert "private" not in repr(safe)
    job = store.submit("videos/reference", "one", {}, None)
    store.finish(job["jobId"], "failed", result)
    info = statistics(store, "history")
    history = info["videos"]["history"][job["jobId"]]
    assert history["httpStatus"] == status
    assert history["nativeModelKey"] == KEY
    assert history["nativeReason"] == reason
    assert "private" not in repr(info)
    summary = info["videos"]["summary"]["public-one"]
    assert summary["rateLimited"] == (status == 429)
    assert summary["failed"] == (status == 403)


def test_unproven_access_reason_is_not_projected_or_classified_as_403(env):
    store, cfg, now = env
    raw = refusal("PUBLIC_ERROR_MODEL_ACCESS_DENIED")
    raw["error"].pop("nativeProof")
    assert http_status(raw, "failed") == 429
    assert "nativeReason" not in error_record(raw, "failed")["errorDetails"]
    job = store.submit("videos/reference", "one", {}, None)
    store.finish(job["jobId"], "failed", raw)
    history = statistics(store, "history")["videos"]["history"][job["jobId"]]
    assert history["httpStatus"] == 429
    assert "nativeReason" not in history


def test_invalid_stored_json_does_not_break_statistics(env):
    store, cfg, now = env
    job = store.submit("videos/reference", "one", {}, None)
    with store.connection() as conn:
        conn.execute(
            "UPDATE jobs SET state='failed',result='invalid JSON' WHERE id=?", (job["jobId"],)
        )
    history = statistics(store, "history")["videos"]["history"][job["jobId"]]
    assert history["httpStatus"] == 502


@pytest.mark.parametrize("field", ["outcomeUnknown", "outcome_unknown"])
def test_unknown_top_level_prevents_all_positive_quota_projection(env, field):
    from gflow_cli import json_output
    from gflow_cli.errors import NativeQuotaError
    from gflow_cli.selfhost import runtime

    store, cfg, now = env
    result = refusal(DAILY)
    result[field] = True
    assert http_status(result, "failed") == 502
    assert error_record(result, "failed")["outcomeUnknown"] is True
    assert "nativeReason" not in error_record(result, "failed")["errorDetails"]
    job = store.submit("videos/reference", "one", {}, None)
    store.finish(job["jobId"], "failed", result)
    history = statistics(store, "history")["videos"]["history"][job["jobId"]]
    assert history["httpStatus"] == 502
    assert "nativeReason" not in history
    private = json_output.error_payload(NativeQuotaError(DAILY, route="example"))
    private[field] = True
    assert runtime.native_refusal_error(private, 4) is None
