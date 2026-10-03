"""Bounded private account identity marker reads; never expose raw file errors."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

_EMAIL = re.compile(r'[^\s"<>]{1,128}@[^\s"<>]{1,125}\Z')


def read_verified_account(profile: Path) -> str | None:
    """Read only the same regular .gflow_account file, at most 1024 UTF-8 bytes."""
    path = profile / ".gflow_account"
    fd: int | None = None
    try:
        if profile.is_symlink():
            return None
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > 1024:
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size > 1024
        ):
            return None
        chunks: list[bytes] = []
        remaining = 1025
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after_fd = os.fstat(fd)
        after = path.lstat()
        if (
            len(raw) > 1024
            or not stat.S_ISREG(after.st_mode)
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or (before.st_size, before.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns)
            or (after_fd.st_size, after_fd.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns)
            or (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns)
        ):
            return None
        value = raw.decode("utf-8").strip()
        return value if _EMAIL.fullmatch(value) else None
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        if fd is not None:
            os.close(fd)
