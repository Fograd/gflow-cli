"""Explicit single-use supplied tokens, isolated by native project and action."""

from __future__ import annotations

import os
import stat
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError

_ACTIONS = {"IMAGE_GENERATION", "VIDEO_GENERATION", "AUDIO_GENERATION"}


@dataclass(repr=False)
class _NativeToken:
    value: str = field(repr=False)
    project: str
    action: str
    consumed: bool = False


_SCOPE: ContextVar[_NativeToken | None] = ContextVar("gflow_native_supplied_token", default=None)


def validate_native_captcha_token(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 20 <= len(value) <= 20000
        or "\x00" in value
        or any(c.isspace() for c in value)
    ):
        raise ConfigurationError(
            detail="Supplied CAPTCHA token requires one bounded nonempty token"
        )
    return value


@contextmanager
def native_captcha_token(value: object, *, project_id: str, action: str) -> Generator[None]:
    """Install one project/action-bound native token; never install a provider retry loop."""
    try:
        project = validate_identifier(project_id)
    except ValueError:
        raise ConfigurationError(detail="Native CAPTCHA scope requires a project UUID") from None
    if action not in _ACTIONS:
        raise ConfigurationError(
            detail="Native CAPTCHA scope requires an observed generation action"
        )
    state = _NativeToken(validate_native_captcha_token(value), project, action)
    handle = _SCOPE.set(state)
    try:
        yield None
    finally:
        state.value = ""
        state.consumed = True
        _SCOPE.reset(handle)


def take_native_captcha_token(page_url: object, action: str) -> str | None:
    """Synchronous consumption: child tasks share one state; independent scopes do not."""
    state = _SCOPE.get()
    if state is None:
        return None
    try:
        if not isinstance(page_url, str):
            raise ValueError
        url = urlsplit(page_url)
        if (
            url.scheme != "https"
            or url.netloc != "flow.google.com"
            or url.path.rstrip("/") != "/project/" + state.project
            or action != state.action
            or state.consumed
        ):
            raise ValueError
    except ValueError:
        raise ConfigurationError(
            detail="Supplied native CAPTCHA scope mismatch or token already consumed"
        ) from None
    state.consumed = True
    value = state.value
    state.value = ""
    return value


def read_native_token_file(path: Path) -> str:
    """Read a private regular owned file without exposing its contents or path in errors."""
    descriptor = None
    try:
        if path.is_symlink():
            raise ValueError
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        info = os.fstat(descriptor)
        named = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)
            or info.st_mode & 0o077
            or info.st_size > 20002
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
        ):
            raise ValueError
        value = os.read(descriptor, 20003).decode("utf-8").rstrip("\r\n")
        return validate_native_captcha_token(value)
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError(
            detail="CAPTCHA token file must be private owned regular bounded text"
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def native_captcha_or_none(
    value: str | None, *, project_id: str, action: str
) -> AbstractContextManager[None]:
    """Use an explicit override only when supplied; otherwise preserve browser behavior."""
    return (
        nullcontext()
        if value is None
        else native_captcha_token(value, project_id=project_id, action=action)
    )
