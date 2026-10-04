"""Launch-only session retention for owned verified Chrome profiles."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path


def _marker(profile: Path, name: str, *, secret: bool) -> str | None:
    fd: int | None = None
    try:
        path = profile / name
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_size > 1024
            or before.st_mode & (0o077 if secret else 0o022)
        ):
            return None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        opened = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            return None
        raw = os.read(fd, 1025)
        after = path.lstat()

        def snapshot(value: os.stat_result) -> tuple[int, ...]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_size,
                value.st_mtime_ns,
                value.st_mode,
                value.st_uid,
            )

        if (
            len(raw) > 1024
            or snapshot(before) != snapshot(after)
            or snapshot(opened) != snapshot(os.fstat(fd))
        ):
            return None
        return raw.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def session_retention_args(profile: Path, channel: str | None) -> list[str]:
    """Markers authorize retention only; they never attest current server identity."""
    if channel != "chrome" or os.name != "posix":
        return []
    try:
        info = profile.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or profile.resolve() != profile.absolute()
        ):
            return []
        if _marker(profile, ".gflow_browser_strategy", secret=False) != "chrome":
            return []
        account = _marker(profile, ".gflow_account", secret=True)
        if account is None or re.fullmatch(r'[^\s"<>]{1,128}@[^\s"<>]{1,125}', account) is None:
            return []
        return ["--restore-last-session"]
    except OSError:
        return []
