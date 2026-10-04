"""Private native worker token lifecycle; only the configured offqueue directory."""

from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from gflow_cli.api.native_captcha import native_captcha_token, read_native_token_file
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.config import environment_root


def native_secret_path(payload: dict[str, Any], root: Path) -> Path | None:
    value = payload.get("captchaSecret")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigurationError(detail="Invalid private CAPTCHA input")
    path = Path(value)
    directory = root.resolve() / "captcha-input"
    if (
        directory.is_symlink()
        or path.parent != directory
        or not re.fullmatch(r"[0-9a-f]{64}\.token", path.name)
    ):
        raise ConfigurationError(detail="Invalid private CAPTCHA input")
    return path


@contextmanager
def private_native_captcha(payload: dict[str, Any], project: str, action: str) -> Generator[None]:
    if payload.get("captchaSecret") is None:
        yield
        return
    path = native_secret_path(payload, environment_root())
    if path is None:
        raise ConfigurationError(detail="Private CAPTCHA input unavailable")
    try:
        token = read_native_token_file(path)
    finally:
        path.unlink(missing_ok=True)
    with native_captcha_token(token, project_id=project, action=action):
        yield
