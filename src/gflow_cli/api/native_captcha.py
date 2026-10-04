"""Explicit single-use supplied tokens, isolated by native project and action."""

from __future__ import annotations

import os
import stat
from collections.abc import Awaitable, Callable, Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
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


@dataclass(repr=False)
class _NativeProvider:
    mint: Callable[[Any, str], Awaitable[str]] = field(repr=False)
    project: str
    action: str
    observe: Callable[[str], None] | None = field(default=None, repr=False)
    consumed: bool = False
    ready: bool = False
    submitted: bool = False
    terminal: str | None = None
    closed: bool = False


_PROVIDER: ContextVar[_NativeProvider | None] = ContextVar(
    "gflow_native_captcha_provider", default=None
)


def _provider_scope(page: Any, action: str, state: _NativeProvider) -> None:
    if state.closed:
        raise ConfigurationError(detail="Native CAPTCHA provider scope is closed")
    value = getattr(page, "url", None)
    try:
        if not isinstance(value, str):
            raise ValueError()
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc != "flow.google.com"
            or url.path.rstrip("/") != "/project/" + state.project
            or action != state.action
        ):
            raise ValueError()
    except ValueError:
        raise ConfigurationError(detail="Native CAPTCHA provider scope mismatch") from None


@contextmanager
def native_captcha_provider(
    mint: Callable[[Any, str], Awaitable[str]],
    *,
    project_id: str,
    action: str,
    observe: Callable[[str], None] | None = None,
) -> Generator[None]:
    """Install one explicit provider mint, never an after-Google retry."""
    try:
        project = validate_identifier(project_id)
    except ValueError:
        raise ConfigurationError(detail="Native CAPTCHA scope requires a project UUID") from None
    if action not in _ACTIONS:
        raise ConfigurationError(
            detail="Native CAPTCHA scope requires an observed generation action"
        )
    state = _NativeProvider(mint, project, action, observe)
    handle = _PROVIDER.set(state)
    try:
        yield
    finally:
        try:
            if state.submitted and state.terminal is None:
                native_captcha_outcome("unknown")
        finally:
            state.closed = True
            _PROVIDER.reset(handle)


async def take_native_captcha_token_async(page: Any, action: str) -> str | None:
    """Supplied token wins; child tasks share one provider attempt consumed before await."""
    supplied = take_native_captcha_token(getattr(page, "url", None), action)
    if supplied is not None:
        return supplied
    state = _PROVIDER.get()
    if state is None:
        return None
    _provider_scope(page, action, state)
    if state.consumed:
        raise ConfigurationError(detail="Native CAPTCHA provider already consumed")
    state.consumed = True
    value = await state.mint(page, action)
    _provider_scope(page, action, state)
    result = validate_native_captcha_token(value)
    state.ready = True
    return result


def native_captcha_submission() -> None:
    """Record provider token dispatch immediately before the actual Google fetch."""
    state = _PROVIDER.get()
    if state is None or state.closed or not state.ready or state.submitted:
        return
    state.submitted = True
    if state.observe is not None:
        state.observe("submitted")


def native_captcha_outcome(outcome: Literal["accepted", "rejected", "unknown"]) -> None:
    """Record one positively known acceptance/refusal, otherwise dispatch uncertainty."""
    if outcome not in ("accepted", "rejected", "unknown"):
        raise ValueError("Invalid native CAPTCHA outcome")
    state = _PROVIDER.get()
    if state is None or state.closed or not state.submitted or state.terminal is not None:
        return
    state.terminal = outcome
    if state.observe is not None:
        state.observe(outcome)


def native_captcha_refused() -> bool:
    """Positive refusal evidence for the current dispatched provider attempt only."""
    state = _PROVIDER.get()
    return bool(
        state is not None
        and not state.closed
        and state.ready
        and state.submitted
        and state.terminal == "rejected"
    )


def native_captcha_active() -> bool:
    """Whether an explicit scope is installed, without exposing its credentials."""
    return _SCOPE.get() is not None or ((state := _PROVIDER.get()) is not None and not state.closed)


def native_captcha_supplied_active() -> bool:
    """Whether a supplied-token scope is installed, without exposing token state."""
    return _SCOPE.get() is not None
