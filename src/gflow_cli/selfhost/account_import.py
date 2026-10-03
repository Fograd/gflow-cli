"""Fresh identity/project verification for an owned imported profile."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from gflow_cli.auth import profile_dir
from gflow_cli.errors import AuthMissingError, ConfigurationError
from gflow_cli.profile_lease import ProfileLease
from gflow_cli.selfhost.account_marker import read_verified_account
from gflow_cli.selfhost.profile_import import ImportedProfile


async def reverify_imported_project(imported: ImportedProfile, project: str) -> ImportedProfile:
    """Verify a preserved project, then recapture only the same owned directory."""
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.transports.migrated_video_upload import is_uuid
    from gflow_cli.auth.verification import FlowSessionOutcome, verify_flow_profile

    if not is_uuid(project):
        raise ConfigurationError(detail="Import project identifier must be a UUID")
    target = profile_dir(imported.profile)
    if (
        not imported.matches_private_state(target)
        or read_verified_account(target) != imported.email
    ):
        raise ConfigurationError(detail="Imported profile state changed before activation")
    try:
        async with asyncio.timeout(120):
            status = await verify_flow_profile(target, source="cookie-import-project-refresh")
            if (
                status.outcome is not FlowSessionOutcome.AUTHENTICATED
                or not isinstance(status.user_email, str)
                or status.user_email.casefold() != imported.email.casefold()
            ):
                raise AuthMissingError(detail="Imported account identity could not be verified")
            # The client owns its lease; never nest it inside an outer ProfileLease.
            async with FlowApiClient(profile_dir=target, headless=False) as client:
                await client.list_native_media(project)
        async with ProfileLease(target):
            if read_verified_account(target) != imported.email:
                raise ConfigurationError(detail="Imported profile state changed before activation")
            return replace(imported.recaptured_private_state(target), project_id=project)
    except (AuthMissingError, ConfigurationError):
        raise
    except Exception:
        raise AuthMissingError(
            detail="Imported account project access could not be verified"
        ) from None
