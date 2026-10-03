"""Bounded immutable local MP4 identification snapshot, not a codec decoder."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from gflow_cli.winsec import ensure_profile_hardened

MAX_VIDEO_BYTES = 250 * 1024 * 1024  # Local budget; not a Google limit.


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


@contextmanager
def snapshot_video(path: Path, *, rights_confirmed: object) -> Generator[Path, None, None]:
    """Snapshot a stable regular MP4 privately; always remove the private copy."""
    if rights_confirmed is not True:
        raise ValueError("Explicit upload rights confirmation must be true")
    descriptor = -1
    private: Path | None = None
    exposed = False
    try:
        before = path.lstat()
        if path.suffix.lower() != ".mp4" or not stat.S_ISREG(before.st_mode):
            raise ValueError("Upload requires a regular local MP4")
        if not 12 <= before.st_size <= MAX_VIDEO_BYTES:
            raise ValueError("MP4 exceeds the local identification budget")
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise ValueError("MP4 changed before snapshot")
        private = Path(tempfile.mkdtemp(prefix="gflow-video-"))
        private.chmod(0o700)
        ensure_profile_hardened(private)
        target = private / "upload.mp4"
        with target.open("xb") as stream:
            target.chmod(0o600)
            remaining = opened.st_size
            first = True
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("MP4 was truncated during snapshot")
                if first:
                    first = False
                    box_size = int.from_bytes(chunk[:4], "big")
                    if (
                        len(chunk) < 12
                        or chunk[4:8] != b"ftyp"
                        or not 12 <= box_size <= opened.st_size
                    ):
                        raise ValueError("MP4 requires a bounded leading ftyp box")
                stream.write(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("MP4 grew during snapshot")
            if _identity(os.fstat(descriptor)) != _identity(opened):
                raise ValueError("MP4 changed during snapshot")
            if _identity(path.lstat()) != _identity(opened) or path.is_symlink():
                raise ValueError("MP4 changed during snapshot")
            stream.flush()
            os.fsync(stream.fileno())
        exposed = True
        yield target
    except OSError:
        if exposed:
            raise
        raise ValueError("Local MP4 snapshot could not be safely prepared or removed") from None
    finally:
        original = sys.exc_info()[1]
        close_failed = False
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
        if private is not None:
            try:
                (private / "upload.mp4").unlink(missing_ok=True)
                private.rmdir()
            except OSError:
                if original is not None:
                    original.add_note("Private MP4 snapshot cleanup pending; no automatic retry")
                else:
                    raise ValueError("Private MP4 snapshot cleanup pending") from None
        if close_failed:
            if original is not None:
                original.add_note("Private MP4 descriptor cleanup incomplete; no automatic retry")
            else:
                raise ValueError("Private MP4 descriptor cleanup incomplete") from None
