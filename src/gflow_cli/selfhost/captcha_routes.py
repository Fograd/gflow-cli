"""Authenticated provider routes and pre-queue image control validation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from gflow_cli.selfhost.captcha import PROVIDERS, CaptchaStats, ProviderKeys


def provider_keys() -> ProviderKeys:
    return ProviderKeys(Path.home() / ".config/homelab")


def mount(app: FastAPI, root: Path) -> None:
    prefix = "/v1/google-flow/accounts"

    @app.get(prefix + "/captcha-providers")
    async def get_providers() -> dict[str, Any]:
        return provider_keys().public()

    @app.post(prefix + "/captcha-providers")
    async def set_providers(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return provider_keys().update(payload)
        except ValueError:
            raise HTTPException(
                422, "Only CapSolver and 2Captcha provider keys are supported"
            ) from None

    @app.get(prefix + "/captcha-stats")
    async def stats() -> dict[str, Any]:
        return CaptchaStats(root).public()


def prepare_image_controls(
    payload: dict[str, Any], root: Path, *, persist_token: bool = True
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
        if not isinstance(value, str) or not 20 <= len(value) <= 20000 or "\x00" in value:
            raise HTTPException(422, "captchaToken requires 20 to 20000 characters")
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
        if value != 1:
            raise HTTPException(501, "Google-refusal CAPTCHA retry cycles are not implemented")
    names = value.split(",") if field == "captchaOrder" and isinstance(value, str) else []
    if field == "captchaOrder" and (
        not 1 <= len(names) <= 10 or any(name not in PROVIDERS for name in names)
    ):
        raise HTTPException(422, "captchaOrder supports 1 to 10 CapSolver/2Captcha entries")
    configured = provider_keys().public()
    if not configured or any(name not in configured for name in names):
        raise HTTPException(422, "Requested CAPTCHA providers are not configured")
