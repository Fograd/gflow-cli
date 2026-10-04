"""Bounded text form adapters reuse exact existing JSON route validation."""

from __future__ import annotations

import json
import math
import re
from email import policy
from email.parser import BytesParser
from typing import Any, cast

from fastapi import HTTPException, Request

FORM_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {"type": "object"}},
            "multipart/form-data": {
                "schema": {"type": "object", "additionalProperties": {"type": "string"}}
            },
        },
    }
}

_NUMERIC = frozenset(
    {
        "count",
        "seed",
        "duration",
        "captchaRetry",
        "trimStart",
        "trimEnd",
        "frameStart",
        "frameEnd",
        "startIndex",
        "endIndex",
        "startFrameIndex_1",
        "endFrameIndex_1",
        "maxPages",
        "maxProjects",
        "maxSteps",
        "maxSeconds",
    }
)
_BOOLEAN = frozenset(
    {"async", "enabled", "verified", "rightsConfirmed", "allPages", "includeCatalogs", "localOnly"}
)
_STRUCTURED = frozenset({"media", "mediaGenerationIds"})


def form_value(name: str, raw: str) -> Any:
    """Only documented typed fields are decoded; text and cookie tables stay literal."""
    if name in _NUMERIC | _BOOLEAN | _STRUCTURED:
        try:
            value: Any = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            raise ValueError("Invalid typed form field") from None
        if name in _NUMERIC and (
            type(value) not in {int, float} or (type(value) is float and not math.isfinite(value))
        ):
            raise ValueError("Invalid numeric form field")
        if name in _BOOLEAN and type(value) is not bool:
            raise ValueError("Invalid boolean form field")
        if name in _STRUCTURED and not isinstance(value, list):
            raise ValueError("Invalid collection form field")
        return cast(Any, value)
    return raw


def parse_form(content_type: str, body: bytes) -> dict[str, Any]:
    """Parse bounded MIME text parts with strict duplicate/file/header refusal."""
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("Multipart body exceeds parser limit")
    if len(content_type) > 256 or "\r" in content_type or "\n" in content_type:
        raise ValueError("Invalid multipart header")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    boundary = message.get_boundary()
    if (
        message.get_content_type() != "multipart/form-data"
        or not boundary
        or re.fullmatch(r"[A-Za-z0-9'()+_,./:=? -]{1,70}", boundary) is None
        or not message.is_multipart()
        or message.defects
        or any(getattr(header, "defects", ()) for _, header in message.items())
        or message.preamble not in (None, "")
        or message.epilogue not in (None, "")
    ):
        raise ValueError("Invalid multipart body")
    parts = list(message.iter_parts())
    if not 1 <= len(parts) <= 64:
        raise ValueError("Invalid multipart field count")
    result: dict[str, Any] = {}
    for part in parts:
        if (
            part.is_multipart()
            or part.defects
            or any(getattr(header, "defects", ()) for _, header in part.items())
            or part.get_content_disposition() != "form-data"
            or len(part.get_all("Content-Disposition", [])) != 1
            or len(part.get_all("Content-Type", [])) > 1
            or part.get_filename() is not None
            or part.get("Content-Transfer-Encoding") is not None
            or part.get_content_type() not in {"text/plain", "application/json"}
            or part.get_content_charset("utf-8").casefold() not in {"utf-8", "us-ascii"}
        ):
            raise ValueError("Multipart requires unique text fields")
        name = part.get_param("name", header="Content-Disposition")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", name) is None
            or name in result
        ):
            raise ValueError("Invalid or duplicate multipart field")
        raw = part.get_payload(decode=True)
        if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024:
            raise ValueError("Invalid multipart text")
        result[name] = form_value(name, raw.decode("utf-8"))
    return result


async def parse_payload(request: Request) -> dict[str, Any]:
    """Preserve JSON types or decode bounded text forms without echoing secrets."""
    content_type = request.headers.get("content-type", "application/json")
    try:
        if content_type.partition(";")[0].strip().casefold() == "multipart/form-data":
            return parse_form(content_type, await request.body())
        media_type = content_type.partition(";")[0].strip().casefold()
        if media_type not in {"application/json", ""} and not (
            media_type.startswith("application/") and media_type.endswith("+json")
        ):
            raise ValueError("Unsupported request content type")
        value: Any = await request.json()
        if not isinstance(value, dict):
            raise ValueError("Request requires an object")
        return cast(dict[str, Any], value)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HTTPException(
            422, "Request requires a valid JSON object or unique multipart text fields"
        ) from None
