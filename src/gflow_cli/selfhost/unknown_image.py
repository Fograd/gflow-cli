"""Whitelist typed native image uncertainty without importing CLI diagnostics."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

PHASES = frozenset({"image_submit", "image_dispatch", "image_response", "image_cancelled"})


def _uuid(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 36:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def unknown_image_result(envelope: object, exit_code: int, project: str) -> dict[str, Any] | None:
    """Recognize only the exact class/type/exit contract and matching project."""
    if exit_code != 40 or not isinstance(envelope, dict):
        return None
    error = cast(dict[str, Any], envelope).get("error")
    if not isinstance(error, dict):
        return None
    value = cast(dict[str, Any], error)
    phase = value.get("phase")
    if (
        value.get("class") != "ImageGenerationUnknownError"
        or value.get("type") != "https://gflow-cli.dev/errors/image-generation-unknown"
        or value.get("outcome_unknown") is not True
        or type(value.get("exit_code")) is not int
        or value.get("exit_code") != 40
        or _uuid(value.get("project_id")) != _uuid(project)
        or _uuid(project) is None
        or not isinstance(phase, str)
        or phase not in PHASES
    ):
        return None
    result: dict[str, Any] = {
        "projectId": _uuid(project),
        "error": {
            "code": "submission_outcome_unknown",
            "exit_code": 40,
            "retryable": False,
            "phase": phase,
        },
    }
    for source, destination in (
        ("media_ids", "knownMediaGenerationIds"),
        ("workflow_ids", "knownWorkflowIds"),
    ):
        items = value.get(source, [])
        if not isinstance(items, list) or len(cast(list[Any], items)) > 4:
            continue
        identifiers = [_uuid(item) for item in cast(list[Any], items)]
        safe = list(dict.fromkeys(item for item in identifiers if item is not None))
        if safe:
            result[destination] = safe
    return result
