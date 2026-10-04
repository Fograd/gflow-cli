"""Preserve imported session-cookie semantics only in the owned staged profile."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import cast

from gflow_cli.errors import ConfigurationError
from gflow_cli.profile_lease import ProfileLease
from gflow_cli.selfhost.session_import import CookieTable

_MAX_PREFERENCES_BYTES = 4 * 1024 * 1024


def _reject() -> ConfigurationError:
    return ConfigurationError(
        detail="Owned staged browser session preferences could not be preserved"
    )


def _private_candidate(candidate: Path, mode: int) -> bool:
    if os.name != "nt":
        return not mode & 0o077
    # Windows chmod bits do not describe DACLs. This freshly created candidate
    # carries the marker only after the importer's existing hardening succeeds.
    from gflow_cli.winsec import ACL_MARKER

    try:
        marker = (candidate / ACL_MARKER).lstat()
    except OSError:
        return False
    return stat.S_ISREG(marker.st_mode) and marker.st_size == 0


def prepare_staged_session_restore(
    candidate: Path, table: CookieTable, *, owner_identity: tuple[int, int]
) -> None:
    """Set Chrome restore only for session-cookie imports, before fresh verification.

    Chrome keeps expires=0 rows on close, but prunes them on a normal cold reopen.
    Its restore preference preserves those rows without inventing cookie expiry.
    An owned staged candidate is required; original/registered profiles are refused.
    """
    from gflow_cli.auth import default_profile_root

    if all("expires" in cookie for cookie in table.playwright_cookies()):
        return
    staging = default_profile_root().resolve() / ".cookie-staging"
    if (
        staging.is_symlink()
        or candidate.is_symlink()
        or not candidate.is_dir()
        or not candidate.name.startswith("candidate-")
        or candidate.parent != staging
        or candidate.resolve(strict=True).parent != staging
    ):
        raise _reject()
    with ProfileLease(candidate):
        metadata = candidate.stat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or not _private_candidate(candidate, metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != owner_identity
        ):
            raise _reject()
        default = candidate / "Default"
        preferences = default / "Preferences"
        if (
            default.is_symlink()
            or not default.is_dir()
            or default.resolve(strict=True).parent != candidate
        ):
            raise _reject()
        temporary: Path | None = None
        try:
            before = preferences.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_PREFERENCES_BYTES:
                raise _reject()
            fd = os.open(
                preferences,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            )
            with os.fdopen(fd, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_PREFERENCES_BYTES:
                    raise _reject()
                raw = stream.read(_MAX_PREFERENCES_BYTES + 1)
            if len(raw) > _MAX_PREFERENCES_BYTES:
                raise _reject()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise _reject()
            data = cast("dict[str, object]", data)
            session = data.setdefault("session", {})
            if not isinstance(session, dict):
                raise _reject()
            session = cast("dict[str, object]", session)
            session["restore_on_startup"] = 1
            descriptor, name = tempfile.mkstemp(prefix=".session-restore-", dir=default)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(data, output, ensure_ascii=False, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o600)
            if preferences.is_symlink() or not preferences.is_file():
                raise _reject()
            current = candidate.stat()
            if (current.st_dev, current.st_ino) != owner_identity:
                raise _reject()
            os.replace(temporary, preferences)
            temporary = None
        except (OSError, ValueError, UnicodeError):
            raise _reject() from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
