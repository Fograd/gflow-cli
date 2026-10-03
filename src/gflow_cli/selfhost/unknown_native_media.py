"""Exact typed native media uncertainty projection; never import raw diagnostics."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID


def _uuid(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 36:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _identifiers(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    values = cast(list[Any], value)
    if len(values) > 100:
        return None
    ids = [_uuid(item) for item in values]
    if any(item is None for item in ids):
        return None
    return list(dict.fromkeys(cast(list[str], ids)))


def unknown_native_media_result(
    envelope: object,
    exit_code: int,
    project: str,
    operation: str,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if exit_code != 40 or not isinstance(envelope, dict):
        return None
    raw = cast(dict[str, Any], envelope).get("error")
    if not isinstance(raw, dict):
        return None
    value = cast(dict[str, Any], raw)
    known = _identifiers(value.get("known_media_ids", []))
    pending = _identifiers(value.get("pending_media_ids", []))
    selected = _uuid(project)
    phase = value.get("phase")
    if (
        value.get("class") != "NativeMediaMutationUnknownError"
        or value.get("type") != "https://gflow-cli.dev/errors/native-media-mutation-unknown"
        or value.get("outcome_unknown") is not True
        or type(value.get("exit_code")) is not int
        or value["exit_code"] != 40
        or selected is None
        or _uuid(value.get("project_id")) != selected
        or operation not in {"upload", "archive", "delete"}
        or value.get("operation") != operation
        or not isinstance(phase, str)
        or phase not in {"dispatch", "response", "cancelled"}
        or known is None
        or pending is None
        or set(known) & set(pending)
    ):
        return None
    earlier = prior or {}
    previous = _identifiers(earlier.get("knownMediaGenerationIds", [])) or []
    if operation in {"archive", "delete"}:
        previous += _identifiers(earlier.get("deleted", [])) or []
    acknowledged = list(dict.fromkeys(previous + known))[:100]
    return {
        "projectId": selected,
        "operation": operation,
        "knownMediaGenerationIds": acknowledged,
        "pendingMediaGenerationIds": [item for item in pending if item not in acknowledged],
        "outcomeUnknown": True,
        "error": {
            "code": "submission_outcome_unknown",
            "exit_code": 40,
            "retryable": False,
            "phase": phase,
            "operation": operation,
        },
    }
