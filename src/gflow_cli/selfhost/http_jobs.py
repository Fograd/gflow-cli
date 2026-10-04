"""Safe useapi-shaped HTTP records, independent of private queue execution state."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

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
_NATIVE_UNKNOWN_CODES = {
    "voice_mutation_outcome_unknown",
    "native_video_generation_outcome_unknown",
    "native_video_edit_outcome_unknown",
    "native_video_extension_outcome_unknown",
    "native_video_promotion_outcome_unknown",
}
_ERROR_CODES = _NATIVE_UNKNOWN_CODES | {
    "gflow_command_failed",
    "submission_outcome_unknown",
    "invalid_operation_result",
    "image_output_count_mismatch",
    "image_partial_download",
    "upload_rights_required",
    "google_flow_unusual_activity",
    "google_flow_waf_rejection",
    "google_flow_content_policy",
    "google_flow_native_quota",
    "google_flow_model_access_denied",
}
EXIT_HTTP_STATUS = {
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
        if details.get("exit_code") == 4 and any(
            flags.get(key) is True
            for flags in (details, result)
            for key in ("outcomeUnknown", "outcome_unknown")
        ):
            return 502
        if details.get("code") == "upload_rights_required":
            return 400
        from gflow_cli.selfhost.model_quarantine import job_quota_metadata

        metadata = job_quota_metadata(details)
        if (
            details.get("code") == "google_flow_model_access_denied"
            and metadata is not None
            and metadata["nativeReason"] == "PUBLIC_ERROR_MODEL_ACCESS_DENIED"
            and details.get("exit_code") == 4
        ):
            return 403
        code = details.get("exit_code")
        return EXIT_HTTP_STATUS.get(code, 502) if type(code) is int else 502
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
    for key in ("width", "height"):
        value = item.get(key)
        if type(value) is int and 0 < value <= 100000:
            safe[key] = value
    path = item.get("downloadPath")
    if isinstance(path, str) and _DOWNLOAD.fullmatch(path):
        safe["downloadPath"] = path
    return safe


def _uuid_value(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        canonical = str(UUID(value))
        return canonical if canonical == value.lower() else None
    except ValueError:
        return None


def _native_unknown_handles(result: dict[str, Any]) -> dict[str, Any]:
    raw = result.get("error")
    if not isinstance(raw, dict):
        return {}
    raw = cast(dict[str, Any], raw)
    code = raw.get("code")
    if (
        not isinstance(code, str)
        or code not in _NATIVE_UNKNOWN_CODES
        or raw.get("outcome_unknown") is not True
    ):
        return {}
    if _uuid_value(result.get("projectId")) is None:
        return {}
    if "project_id" in raw and raw["project_id"] != result["projectId"]:
        return {}
    media = raw.get("known_media_ids" if code == "voice_mutation_outcome_unknown" else "media_ids")
    workflows = raw.get("workflow_ids")
    limit = 1 if code == "voice_mutation_outcome_unknown" else 4
    if not isinstance(media, list) or not isinstance(workflows, list):
        return {}
    media, workflows = cast(list[Any], media), cast(list[Any], workflows)
    if not 1 <= len(media) <= limit or len(media) != len(workflows):
        return {}
    canonical_media = [_uuid_value(value) for value in media]
    canonical_workflows = [_uuid_value(value) for value in workflows]
    if None in canonical_media or None in canonical_workflows:
        return {}
    if len(set(canonical_media + canonical_workflows)) != 2 * len(media):
        return {}
    return {"knownMediaGenerationIds": canonical_media, "knownWorkflowIds": canonical_workflows}


def _saved_voice_result(result: dict[str, Any], kind: str | None) -> dict[str, Any]:
    # Sync delivery reprojects Store.public, so a missing kind is accepted only
    # with the complete acknowledged voice identity shape. Other routes fail closed.
    if kind not in (None, "voices/create") or result.get("source") != "user":
        return {}
    identifier = _uuid_value(result.get("ref"))
    workflow = _uuid_value(result.get("workflowId"))
    project = _uuid_value(result.get("projectId"))
    if identifier is None or workflow is None or project is None:
        return {}
    if result.get("mediaId") != identifier or result.get("voice") != identifier:
        return {}
    name = result.get("displayName")
    if not isinstance(name, str) or not 1 <= len(name) <= 200 or "\x00" in name:
        return {}
    safe: dict[str, Any] = {
        "ref": identifier,
        "mediaId": identifier,
        "voice": identifier,
        "workflowId": workflow,
        "source": "user",
        "displayName": name,
    }
    for key, limit in (("baseVoice", 100), ("dialog", 120), ("voicePerformance", 120)):
        value = result.get(key)
        if isinstance(value, str) and len(value) <= limit and "\x00" not in value:
            safe[key] = value
    return safe


def _delete_retry_result(result: dict[str, Any], kind: str | None) -> dict[str, Any]:
    if kind not in (None, "assets/delete") or result.get("operation") != "delete":
        return {}
    if _uuid_value(result.get("projectId")) is None:
        return {}
    groups: dict[str, list[str]] = {}
    for key in ("deleted", "newlyDeleted", "alreadyDeleted"):
        raw = result.get(key)
        if not isinstance(raw, list) or len(cast(list[Any], raw)) > 100:
            return {}
        values = [_uuid_value(value) for value in cast(list[Any], raw)]
        if None in values or len(set(values)) != len(values):
            return {}
        groups[key] = cast(list[str], values)
    count = result.get("deletedCount")
    persisted = result.get("receiptPersisted")
    if (
        not groups["deleted"]
        or type(count) is not int
        or count != len(groups["deleted"])
        or type(persisted) is not bool
        or set(groups["newlyDeleted"]) & set(groups["alreadyDeleted"])
        or set(groups["deleted"]) != set(groups["newlyDeleted"] + groups["alreadyDeleted"])
    ):
        return {}
    return {
        "deletedCount": count,
        "receiptPersisted": persisted,
        "newlyDeleted": groups["newlyDeleted"],
        "alreadyDeleted": groups["alreadyDeleted"],
    }


def result_record(result: dict[str, Any], *, kind: str | None = None) -> dict[str, Any]:
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
        "resolution",
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
    if kind == "videos/edit":
        start, end = result.get("startFrameIndex"), result.get("endFrameIndex")
        if type(start) is int and type(end) is int and 0 <= start < end <= 240:
            safe.update(startFrameIndex=start, endFrameIndex=end)
            measured = result.get("sourceDurationSeconds")
            if (
                isinstance(measured, (int, float))
                and not isinstance(measured, bool)
                and 0 < measured <= 315_576_000
                and math.isfinite(measured)
            ):
                safe["sourceDurationSeconds"] = measured
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
    if (
        kind == "videos/concatenate"
        and type(result.get("inputsCount")) is int
        and 2 <= result["inputsCount"] <= 10
    ):
        safe["inputsCount"] = result["inputsCount"]
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
    safe.update(_delete_retry_result(result, kind))
    safe.update(_saved_voice_result(result, kind))
    safe.update(_native_unknown_handles(result))
    return safe


def error_record(result: dict[str, Any], state: str) -> dict[str, Any]:
    raw = result.get("error")
    raw = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    code = raw.get("code")
    code = code if isinstance(code, str) and code in _ERROR_CODES else "operation_failed"
    unknown = (
        state == "interrupted"
        or (
            code in {"google_flow_native_quota", "google_flow_model_access_denied"}
            and any(
                flags.get(key) is True
                for flags in (raw, result)
                for key in ("outcomeUnknown", "outcome_unknown")
            )
        )
        or code == "submission_outcome_unknown"
        or raw.get("exit_code") == 9
        or (code in _NATIVE_UNKNOWN_CODES and raw.get("outcome_unknown") is True)
    )
    detail = (
        "Submission outcome is unknown; inspect this job and Flow before another request."
        if unknown
        else "Google Flow operation failed; inspect this job before another request."
    )
    if code == "upload_rights_required":
        detail = "Video upload requires an explicit rights confirmation for this request."
    elif code == "google_flow_unusual_activity":
        detail = "Google Flow refused this request because of unusual activity."
    elif code == "google_flow_waf_rejection":
        detail = "Google Flow refused this request at its browser protection check."
    elif code == "google_flow_content_policy":
        detail = "Google Flow refused this request under its content policy."
    safe: dict[str, Any] = {
        "error": detail,
        "code": http_status(result, state),
        "errorDetails": {"code": code},
        "retryable": False,
    }
    exit_code = raw.get("exit_code")
    if type(exit_code) is int:
        safe["errorDetails"]["exit_code"] = exit_code
    if not unknown and code in {"google_flow_native_quota", "google_flow_model_access_denied"}:
        from gflow_cli.selfhost.model_quarantine import job_quota_metadata

        metadata = job_quota_metadata(raw)
        if metadata is not None and raw.get("exit_code") == 4:
            safe["errorDetails"].update(metadata)
            safe["error"] = (
                "Google Flow denied access to this native model."
                if metadata["nativeReason"] == "PUBLIC_ERROR_MODEL_ACCESS_DENIED"
                else "Google Flow refused this request under a native quota or throttle."
            )
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
        if code in _NATIVE_UNKNOWN_CODES:
            native_phases = (
                {"preview", "save", "delete"}
                if code == "voice_mutation_outcome_unknown"
                else {"video_submit", "video_poll"}
            )
            if isinstance(phase, str) and phase in native_phases:
                safe["errorDetails"]["phase"] = phase
            handles = _native_unknown_handles(result)
            safe.update(handles)
            if handles:
                safe["errorDetails"]["media_ids"] = handles["knownMediaGenerationIds"]
                safe["errorDetails"]["workflow_ids"] = handles["knownWorkflowIds"]
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
    safe_result = result_record(result, kind=row["kind"])
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
