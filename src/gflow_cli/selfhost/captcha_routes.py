"""Authenticated provider routes and pre-queue image control validation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from gflow_cli.selfhost.captcha import PROVIDERS, CaptchaStats, ProviderKeys
from gflow_cli.selfhost.form_payload import FORM_REQUEST_BODY, parse_payload


def provider_keys() -> ProviderKeys:
    return ProviderKeys(Path.home() / ".config/homelab")


def mount(app: FastAPI, root: Path) -> None:
    prefix = "/v1/google-flow/accounts"

    @app.get(prefix + "/captcha-providers")
    async def get_providers() -> dict[str, Any]:
        return provider_keys().public()

    @app.post(prefix + "/captcha-providers", openapi_extra=FORM_REQUEST_BODY)
    async def set_providers(
        payload: Annotated[dict[str, Any], Depends(parse_payload)],
    ) -> dict[str, Any]:
        try:
            return provider_keys().update(payload)
        except ValueError:
            raise HTTPException(
                422, "Only CapSolver and 2Captcha provider keys are supported"
            ) from None

    @app.get(prefix + "/captcha-stats")
    async def stats(request: Request) -> dict[str, Any]:
        from gflow_cli.selfhost.captcha_events import query_events

        params = request.query_params
        if set(params) - {"date", "limit", "provider", "anonymized"}:
            raise HTTPException(400, "Unknown CAPTCHA statistics filters")
        if params.get("anonymized", "false") not in {"true", "false"}:
            raise HTTPException(400, "anonymized requires true or false")
        if params.get("anonymized") == "true":
            raise HTTPException(501, "Vendor-wide anonymized statistics are unavailable locally")
        try:
            raw_limit = params.get("limit")
            limit = int(raw_limit) if raw_limit is not None else None
            result = query_events(
                root, date=params.get("date"), limit=limit, provider=params.get("provider")
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return {**CaptchaStats(root).public(), **result}


def prepare_image_controls(
    payload: dict[str, Any], root: Path, *, persist_token: bool = True, native_retry: bool = False
) -> None:
    fields = [
        field for field in ("captchaToken", "captchaRetry", "captchaOrder") if field in payload
    ]
    if len(fields) > 1:
        raise HTTPException(422, "CAPTCHA controls are mutually exclusive")
    if not fields:
        return
    field = fields[0]
    value = payload[field]
    if field == "captchaToken":
        if (
            not isinstance(value, str)
            or not 20 <= len(value) <= 20000
            or "\x00" in value
            or any(character.isspace() for character in value)
        ):
            raise HTTPException(
                422, "captchaToken requires 20 to 20000 characters without whitespace"
            )
        directory = root / "captcha-input"
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (hashlib.sha256(value.encode()).hexdigest() + ".token")
        if persist_token:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(value)
        payload.pop(field)
        payload["captchaSecret"] = str(path)
        return
    if field == "captchaRetry":
        if type(value) is not int or not 1 <= value <= 10:
            raise HTTPException(422, "captchaRetry requires an integer from 1 to 10")
        if value != 1 and not native_retry:
            raise HTTPException(501, "Google-refusal CAPTCHA retry cycles are not implemented")
    names = value.split(",") if field == "captchaOrder" and isinstance(value, str) else []
    if field == "captchaOrder" and (
        not 1 <= len(names) <= 10
        or len(set(names)) != len(names)
        or any(name not in PROVIDERS for name in names)
    ):
        raise HTTPException(422, "captchaOrder supports 1 to 10 CapSolver/2Captcha entries")
    configured = provider_keys().public()
    if not configured or any(name not in configured for name in names):
        raise HTTPException(422, "Requested CAPTCHA providers are not configured")
