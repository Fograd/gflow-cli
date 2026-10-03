"""Safe useapi-shaped HTTP records, independent of private queue execution state."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any, cast

_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_DOWNLOAD = re.compile(r"/v1/google-flow/assets/[A-Za-z0-9_-]{1,160}/download")
_REQUEST_STRINGS = {
    "prompt",
    "email",
    "model",
    "aspectRatio",
    "resolution",
    "projectId",
    "replyUrl",
    "replyRef",
    "startImage",
    "endImage",
    "mediaGenerationId",
}
_REQUEST_NUMBERS = {"count", "duration", "seed"}
_ERROR_CODES = {
    "gflow_command_failed",
    "submission_outcome_unknown",
    "invalid_operation_result",
    "image_output_count_mismatch",
    "image_partial_download",
    "upload_rights_required",
}
_EXIT_HTTP = {
    3: 596,
    8: 596,
    38: 596,
    4: 429,
    5: 400,
    9: 408,
    10: 403,
    11: 400,
    17: 400,
    18: 400,
    22: 403,
    27: 400,
    32: 404,
    37: 402,
    39: 403,
}


def http_status(result: dict[str, Any], state: str) -> int:
    if state == "interrupted":
        return 502
    error = result.get("error")
    if isinstance(error, dict):
        details = cast(dict[str, Any], error)
        if details.get("code") == "upload_rights_required":
            return 400
        code = details.get("exit_code")
        return _EXIT_HTTP.get(code, 502) if type(code) is int else 502
    return 502


def aspect_metadata(payload: dict[str, Any]) -> dict[str, str]:
    if (
        payload.get("requestedAspectRatio") == "auto"
        and payload.get("resolvedAspectRatio") in ("16:9", "4:3", "1:1", "3:4", "9:16")
        and payload.get("aspectPolicy") == "derived-first-reference-nearest-supported-v1"
    ):
        return {
            key: payload[key]
            for key in ("requestedAspectRatio", "resolvedAspectRatio", "aspectPolicy")
        }
    return {}


def request_record(payload: dict[str, Any]) -> dict[str, Any]:
    """Whitelist primitive request fields; never echo token/ref paths or worker controls."""
    request: dict[str, Any] = {}
    for key, value in payload.items():
        slot = re.fullmatch(r"(?:reference|referenceImage|character)_[1-9][0-9]?", key)
        if (key in _REQUEST_STRINGS or slot) and isinstance(value, str):
            request[key] = value
        elif key in _REQUEST_NUMBERS and type(value) is int:
            request[key] = value
    if aspect_metadata(payload):
        request["aspectRatio"] = "auto"
    if type(payload.get("_delivery_async")) is bool:
        request["async"] = payload["_delivery_async"]
    media = payload.get("media")
    if isinstance(media, list):
        request["media"] = [
            {
                key: value
                for key, value in cast(dict[str, Any], item).items()
                if (key == "mediaGenerationId" and isinstance(value, str) and _ID.fullmatch(value))
                or (key in ("trimStart", "trimEnd") and type(value) in (int, float))
            }
            for item in cast(list[Any], media)[:10]
            if isinstance(item, dict)
        ]
    ids = payload.get("mediaGenerationIds")
    if isinstance(ids, list):
        request["mediaGenerationIds"] = [
            value
            for value in cast(list[Any], ids)[:100]
            if isinstance(value, str) and _ID.fullmatch(value)
        ]
    return request


def _media(item: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in (
        "name",
        "mediaGenerationId",
        "workflowId",
        "projectId",
        "localArtifactId",
        "sourceMediaGenerationId",
    ):
        value = item.get(key)
        if isinstance(value, str) and _ID.fullmatch(value):
            safe[key] = value
    for arm, generated in (("image", "generatedImage"), ("video", "generatedVideo")):
        value = item.get(arm)
        if not isinstance(value, dict):
            continue
        arm_value = cast(dict[str, Any], value)
        fields: dict[str, Any] = {}
        path = arm_value.get("downloadPath")
        if isinstance(path, str) and _DOWNLOAD.fullmatch(path):
            fields["downloadPath"] = path
        nested = arm_value.get(generated)
        if isinstance(nested, dict):
            output: dict[str, Any] = {}
            for key, data in cast(dict[str, Any], nested).items():
                if key in ("seed", "width", "height") and type(data) is int:
                    output[key] = data
                elif key == "mediaGenerationId" and isinstance(data, str) and _ID.fullmatch(data):
                    output[key] = data
                elif key in ("encodedImage", "encodedVideo", "rawBytes") and isinstance(data, str):
                    if len(data) <= 28 * 1024 * 1024 and re.fullmatch(r"[A-Za-z0-9+/=]*", data):
                        output[key] = data
            if output:
                fields[generated] = output
        if fields:
            safe[arm] = fields
    path = item.get("downloadPath")
    if isinstance(path, str) and _DOWNLOAD.fullmatch(path):
        safe["downloadPath"] = path
    return safe


def result_record(result: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    media = result.get("media")
    if isinstance(media, list):
        safe["media"] = [
            _media(cast(dict[str, Any], item))
            for item in cast(list[Any], media)[:10]
            if isinstance(item, dict)
        ]
    for key in (
        "email",
        "projectId",
        "backend",
        "mediaGenerationId",
        "sourceMediaGenerationId",
        "localArtifactId",
        "scope",
        "kind",
        "operation",
        "requestedAspectRatio",
        "resolvedAspectRatio",
        "aspectPolicy",
    ):
        value = result.get(key)
        if isinstance(value, str) and len(value) <= 200 and "/" not in value:
            safe[key] = value
    for key in (
        "generatedCount",
        "completedCount",
        "expectedCount",
        "receivedCount",
        "width",
        "height",
        "bytes",
    ):
        value = result.get(key)
        if type(value) is int and value >= 0:
            safe[key] = value
    ids = result.get("knownMediaGenerationIds")
    if isinstance(ids, list):
        safe["knownMediaGenerationIds"] = [
            value
            for value in cast(list[Any], ids)[:100]
            if isinstance(value, str) and _ID.fullmatch(value)
        ]
    pending = result.get("pendingMediaGenerationIds")
    if isinstance(pending, list):
        safe["pendingMediaGenerationIds"] = [
            value
            for value in cast(list[Any], pending)[:100]
            if isinstance(value, str) and _ID.fullmatch(value)
        ]
    workflow_ids = result.get("knownWorkflowIds")
    if isinstance(workflow_ids, list):
        safe["knownWorkflowIds"] = [
            item
            for item in cast(list[Any], workflow_ids)[:4]
            if isinstance(item, str) and _ID.fullmatch(item)
        ]
    for key in ("deleted",):
        values = result.get(key)
        if isinstance(values, list):
            safe[key] = [
                value
                for value in cast(list[Any], values)[:100]
                if isinstance(value, str) and _ID.fullmatch(value)
            ]
    for key in ("googleLibraryModified", "localCacheModified"):
        if type(result.get(key)) is bool:
            safe[key] = result[key]
    duration = result.get("duration")
    if (
        type(duration) in (int, float)
        and math.isfinite(cast(float, duration))
        and cast(float, duration) >= 0
    ):
        safe["duration"] = duration
    uploaded = result.get("mediaGenerationId")
    if isinstance(uploaded, dict):
        identifier = cast(dict[str, Any], uploaded).get("mediaGenerationId")
        if isinstance(identifier, str) and _ID.fullmatch(identifier):
            safe["mediaGenerationId"] = {"mediaGenerationId": identifier}
    for key in ("encodedGif", "encodedVideo", "encodedImage"):
        value = result.get(key)
        if isinstance(value, str) and len(value) <= 28 * 1024 * 1024:
            if re.fullmatch(r"[A-Za-z0-9+/=]*", value):
                safe[key] = value
    path = result.get("downloadPath")
    if isinstance(path, str) and _DOWNLOAD.fullmatch(path):
        safe["downloadPath"] = path
    if "sessionHealth" in result:
        from gflow_cli.selfhost.session_health import public_health_observation

        safe["sessionHealth"] = public_health_observation(result["sessionHealth"])
    return safe


def error_record(result: dict[str, Any], state: str) -> dict[str, Any]:
    raw = result.get("error")
    raw = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    code = raw.get("code")
    code = code if isinstance(code, str) and code in _ERROR_CODES else "operation_failed"
    unknown = (
        state == "interrupted" or code == "submission_outcome_unknown" or raw.get("exit_code") == 9
    )
    detail = (
        "Submission outcome is unknown; inspect this job and Flow before another request."
        if unknown
        else "Google Flow operation failed; inspect this job before another request."
    )
    if code == "upload_rights_required":
        detail = "Video upload requires an explicit rights confirmation for this request."
    safe: dict[str, Any] = {
        "error": detail,
        "code": http_status(result, state),
        "errorDetails": {"code": code},
        "retryable": False,
    }
    exit_code = raw.get("exit_code")
    if type(exit_code) is int:
        safe["errorDetails"]["exit_code"] = exit_code
    if unknown:
        safe["outcomeUnknown"] = True
        from gflow_cli.selfhost.unknown_image import PHASES

        phase = raw.get("phase")
        operation = raw.get("operation")
        allowed_phases = PHASES | (
            {"dispatch", "response", "cancelled"}
            if operation in ("upload", "archive")
            else set[str]()
        )
        if operation in ("upload", "archive"):
            safe["errorDetails"]["operation"] = operation
        if isinstance(phase, str) and phase in allowed_phases:
            safe["errorDetails"]["phase"] = phase
    return safe


def job_record(row: Any, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    state = row["state"]
    status = "started" if state == "running" else "failed" if state == "interrupted" else state
    record: dict[str, Any] = {
        "jobid": row["id"],
        "jobId": row["id"],
        "type": "video"
        if row["kind"].startswith("videos")
        else "image"
        if row["kind"].startswith("images")
        else "asset",
        "status": status,
        "created": datetime.fromtimestamp(row["created"], UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "updated": datetime.fromtimestamp(row["updated"], UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "createdAt": row["created"],
        "updatedAt": row["updated"],
        "request": request_record(payload),
    }
    record.update(aspect_metadata(payload))
    safe_result = result_record(result)
    if safe_result:
        record["response"] = safe_result
        # Preserve existing protected-media and recovery consumers, without raw worker fields.
        record.update(
            {
                key: value
                for key, value in safe_result.items()
                if key not in ("media", "encodedGif", "encodedVideo", "encodedImage")
            }
        )
    if "replyRef" in record["request"]:
        record["replyRef"] = record["request"]["replyRef"]
    if state in ("failed", "interrupted"):
        record.update(error_record(result, state))
    return record
