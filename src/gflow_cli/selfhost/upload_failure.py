"""Bounded upload branch observations from exact canonical CLI error envelopes."""

from __future__ import annotations

import re
from typing import Any, cast

UPLOAD_FAILURE_REASONS = frozenset(
    {
        "http_error",
        "acknowledgement_unconfirmed",
        "response_timeout_after_dispatch",
        "not_dispatched",
        "dialog_blocked",
        "unclassified",
    }
)


def media_upload_failure(envelope: object, exit_code: int) -> dict[str, Any] | None:
    """Project source-generated branch observations, never arbitrary error prose."""
    if exit_code != 27 or not isinstance(envelope, dict):
        return None
    raw = cast(dict[str, Any], envelope).get("error")
    if not isinstance(raw, dict):
        return None
    error = cast(dict[str, Any], raw)
    if (
        error.get("class") != "MediaUploadRejectedError"
        or error.get("type") != "https://gflow-cli.dev/errors/media-upload-rejected"
        or type(error.get("exit_code")) is not int
        or error["exit_code"] != 27
    ):
        return None
    status = error.get("status")
    status = status if type(status) is int and 100 <= status <= 599 else None
    reason = "unclassified"
    detail = error.get("detail")
    if error.get("route") == "batchexecute:maseQ" and isinstance(detail, str):
        if (
            status is not None
            and status != 200
            and detail == (f"migrated host: the upload rpc maseQ answered HTTP {status}")
        ):
            reason = "http_error"
        elif status == 200 and detail == (
            "migrated host: maseQ answered 200 without a media id "
            "confirmed for the requested project id"
        ):
            reason = "acknowledgement_unconfirmed"
        elif detail == (
            "migrated host: a dialog opened after the file was chosen and no "
            "maseQ request left the page — most likely Flow's one-time "
            "upload-terms confirmation (host=migrated)"
        ):
            reason = "dialog_blocked"
        else:
            timeout = re.fullmatch(
                r"migrated host: no maseQ reply within [1-9][0-9]{0,3}s of choosing the file — "
                r"(the request left the page and Flow did not answer in time|"
                r"no upload request ever left the page)",
                detail,
            )
            if timeout is not None:
                reason = (
                    "response_timeout_after_dispatch"
                    if timeout.group(1).startswith("the request")
                    else "not_dispatched"
                )
    return {
        "code": "gflow_command_failed",
        "exit_code": 27,
        "retryable": False,
        "operation": "upload",
        "uploadReason": reason,
        **(
            {"nativeHttpStatus": status}
            if reason in {"http_error", "acknowledgement_unconfirmed"}
            else {}
        ),
    }
