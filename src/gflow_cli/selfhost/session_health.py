"""On-demand, queue-serialized native project access; never changes authentication."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any, cast

from gflow_cli.auth import default_profile_root, profile_dir
from gflow_cli.errors import AuthExpiredError, AuthMissingError, ProfileLockedError
from gflow_cli.selfhost.account_marker import read_verified_account

HEALTH_TIMEOUT = 90
_REASONS = frozenset(
    {
        "project_access_verified",
        "identity_unavailable",
        "identity_changed",
        "profile_busy",
        "login_required",
        "probe_timeout",
        "probe_error",
        "invalid_registration",
        "interrupted",
    }
)


def health_observation(health: str = "UNKNOWN", reason: str = "probe_error") -> dict[str, Any]:
    """Construct only fixed public metadata, without principal or browser details."""
    return {
        "health": health if health in {"OK", "LOGIN_REQUIRED", "UNKNOWN"} else "UNKNOWN",
        "reason": reason if reason in _REASONS else "probe_error",
        "source": "native-project-access",
        "checkedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "profilePreserved": True,
        "refreshAttempted": False,
    }


async def probe_project_access(profile: object, project: str) -> dict[str, Any]:
    """Probe an existing mapped profile from its serialized worker, not a parallel route.

    A successful read proves project access only at checkedAt. The bounded private
    marker is checked for consistency; this is not a fresh Google principal proof
    or a promise of future access. The caller must serialize with generation jobs.
    """
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.transports.migrated_video_upload import is_uuid

    if (
        not isinstance(profile, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile)
        or not is_uuid(project)
    ):
        return health_observation(reason="invalid_registration")
    target = profile_dir(profile)
    if target.is_symlink() or target.parent.resolve() != default_profile_root().resolve():
        return health_observation(reason="invalid_registration")
    identity = read_verified_account(target)
    if identity is None:
        return health_observation(reason="identity_unavailable")
    try:
        async with asyncio.timeout(HEALTH_TIMEOUT):
            async with FlowApiClient(profile_dir=target, headless=False) as client:
                await client.list_native_media(project)
                if read_verified_account(target) != identity:
                    return health_observation(reason="identity_changed")
        # The existing client completes its bounded teardown before this result.
        if read_verified_account(target) != identity:
            return health_observation(reason="identity_changed")
        return health_observation("OK", "project_access_verified")
    except ProfileLockedError:
        return health_observation(reason="profile_busy")
    except (AuthMissingError, AuthExpiredError):
        return health_observation("LOGIN_REQUIRED", "login_required")
    except TimeoutError:
        return health_observation(reason="probe_timeout")
    except Exception:
        return health_observation(reason="probe_error")


def public_health_observation(raw: object) -> dict[str, Any]:
    """Whitelist a worker observation; malformed/private payloads become unknown."""
    if not isinstance(raw, dict):
        return health_observation()
    value = cast(dict[str, Any], raw)
    status, reason, checked = value.get("health"), value.get("reason"), value.get("checkedAt")
    if (
        not isinstance(status, str)
        or status not in {"OK", "LOGIN_REQUIRED", "UNKNOWN"}
        or not isinstance(reason, str)
        or reason not in _REASONS
        or value.get("source") != "native-project-access"
        or not isinstance(checked, str)
        or len(checked) > 32
        or value.get("profilePreserved") is not True
        or value.get("refreshAttempted") is not False
        or (status == "OK" and reason != "project_access_verified")
    ):
        return health_observation()
    try:
        stamp = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return health_observation()
    except ValueError:
        return health_observation()
    return {
        **health_observation(status, reason),
        "checkedAt": stamp.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
