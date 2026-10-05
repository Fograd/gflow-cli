"""On-demand, queue-serialized native project access; never changes authentication."""

from __future__ import annotations

import asyncio
import hashlib
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
        "registration_changed",
        "cleanup_incomplete",
    }
)


def health_observation(
    health: str = "UNKNOWN", reason: str = "probe_error", *, identity_verified: bool = False
) -> dict[str, Any]:
    """Construct only fixed public metadata, without principal or browser details."""
    return {
        "health": health if health in {"OK", "LOGIN_REQUIRED", "UNKNOWN"} else "UNKNOWN",
        "reason": reason if reason in _REASONS else "probe_error",
        "source": "native-project-access",
        "checkedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "profilePreserved": True,
        "refreshAttempted": False,
        "identityVerified": identity_verified is True and health == "OK",
    }


def profile_identity_sha256(profile: str) -> str | None:
    """Private expected-principal anchor; never a Google credential or public field."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile):
        return None
    target = profile_dir(profile)
    if target.is_symlink() or target.parent.resolve() != default_profile_root().resolve():
        return None
    identity = read_verified_account(target)
    return hashlib.sha256(identity.casefold().encode()).hexdigest() if identity else None


async def probe_project_access(
    profile: object, project: str, *, expected_identity_sha256: str | None = None
) -> dict[str, Any]:
    """Probe an existing mapped profile from its serialized worker, not a parallel route.

    A successful read proves project access only at checkedAt. The bounded private
    marker and an admission-pinned expected principal are checked against fresh
    Google identity on both sides of the project read. This is not renewal or a
    promise of future access. The caller must serialize with generation jobs.
    """
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.transports.migrated_rpc import (
        NativeIdentityHttpError,
        NativeMetadataRpcError,
    )
    from gflow_cli.api.transports.migrated_video_upload import is_uuid
    from gflow_cli.auth.native_identity import read_native_identity

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
    expected = hashlib.sha256(identity.casefold().encode()).hexdigest()
    if expected_identity_sha256 is not None and expected != expected_identity_sha256:
        return health_observation(reason="identity_changed")
    try:
        async with asyncio.timeout(HEALTH_TIMEOUT):
            async with FlowApiClient(profile_dir=target, headless=False) as client:
                page = client._page  # pyright: ignore[reportPrivateUsage]
                if page is None:
                    return health_observation(reason="identity_unavailable")
                principal = await read_native_identity(page)
                if hashlib.sha256(principal.casefold().encode()).hexdigest() != expected:
                    return health_observation(reason="identity_changed")
                await client.list_native_media(project)
                principal = await read_native_identity(page)
                if hashlib.sha256(principal.casefold().encode()).hexdigest() != expected:
                    return health_observation(reason="identity_changed")
                if read_verified_account(target) != identity:
                    return health_observation(reason="identity_changed")
        # The existing client completes its bounded teardown before this result.
        if client.browser_teardown_succeeded is not True:
            return health_observation(reason="cleanup_incomplete")
        if read_verified_account(target) != identity:
            return health_observation(reason="identity_changed")
        return health_observation("OK", "project_access_verified", identity_verified=True)
    except ProfileLockedError:
        return health_observation(reason="profile_busy")
    except (AuthMissingError, AuthExpiredError):
        return health_observation("LOGIN_REQUIRED", "login_required")
    except NativeIdentityHttpError as exc:
        # A generic403 or unrelated read failure is not proof of lost authentication.
        return (
            health_observation("LOGIN_REQUIRED", "login_required")
            if exc.status == 401
            else health_observation(reason="identity_unavailable")
        )
    except NativeMetadataRpcError as exc:
        return (
            health_observation("LOGIN_REQUIRED", "login_required")
            if exc.rpcid == "o30O0e" and exc.code == 16
            else health_observation(reason="identity_unavailable")
        )
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
        or (status == "LOGIN_REQUIRED" and reason != "login_required")
        or (status == "UNKNOWN" and reason in {"login_required", "project_access_verified"})
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
        "identityVerified": value.get("identityVerified") is True and status == "OK",
    }
