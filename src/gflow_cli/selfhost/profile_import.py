"""Private staged cookie import. Existing profiles are never overwritten."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import structlog

from gflow_cli.errors import AuthMissingError, ConfigurationError
from gflow_cli.profile_lease import ProfileLease
from gflow_cli.selfhost.session_import import CookieTable
from gflow_cli.selfhost.session_restore import prepare_staged_session_restore


@dataclass(frozen=True)
class ImportedProfile:
    profile: str
    email: str
    project_id: str
    cookie_count: int
    _identity: tuple[int, int] | None = field(default=None, repr=False)
    _fingerprint: tuple[tuple[str, int, int, int, int], ...] = field(default=(), repr=False)
    scope: str = "verified staged profile; account registration is separate"

    def same_directory_identity(self, target: Path) -> bool:
        if target.is_symlink() or not target.is_dir() or self._identity is None:
            return False
        stat = target.stat()
        return (stat.st_dev, stat.st_ino) == self._identity

    def recaptured_private_state(self, target: Path) -> ImportedProfile:
        """Call only after a fresh identity/access probe of this owned directory."""
        from gflow_cli.selfhost.account_marker import read_verified_account

        if not self.same_directory_identity(target) or read_verified_account(target) != self.email:
            raise ConfigurationError(detail="Imported profile was replaced")
        return replace(self, _fingerprint=_fingerprint(target))

    def matches_private_state(self, target: Path) -> bool:
        if target.is_symlink() or not target.is_dir() or self._identity is None:
            return False
        stat = target.stat()
        return (stat.st_dev, stat.st_ino) == self._identity and _fingerprint(
            target
        ) == self._fingerprint


def _reject() -> AuthMissingError:
    return AuthMissingError(
        detail="Imported cookies did not prove the expected Google account and Flow access",
        remediation_hint="Complete login in the hosted browser, then retry with a fresh session.",
    )


async def _populate_candidate(candidate: Path, table: CookieTable) -> None:
    from gflow_cli.api._engine import close_context_bounded
    from gflow_cli.auth.internal_chromium import login_launch_kwargs
    from gflow_cli.auth.strategies import async_playwright
    from gflow_cli.browser_manager import ensure_profile_engine_compatible

    async with ProfileLease(candidate), async_playwright() as pw:
        ensure_profile_engine_compatible(candidate, "chrome")
        ctx = await pw.chromium.launch_persistent_context(
            **login_launch_kwargs(candidate, False, channel="chrome")
        )
        closed = False
        try:
            await ctx.add_cookies(cast("Any", table.playwright_cookies()))
            page = await ctx.new_page()
            await page.goto(
                "https://labs.google/fx/tools/flow?hl=en",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            # Native redirect/session establishment may happen client-side.
            await page.wait_for_timeout(3000)
        finally:
            closed = await close_context_bounded(ctx, owner="cookie-import")
        if not closed:
            raise _reject()


async def _verify_candidate(
    candidate: Path, expected_email: str | None, project_id: str | None
) -> tuple[str, str]:
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.auth.verification import FlowSessionOutcome, verify_flow_profile

    status = (
        await verify_flow_profile(candidate, source="cookie-import", project_id=project_id)
        if project_id is not None
        else await verify_flow_profile(candidate, source="cookie-import")
    )
    email = status.user_email
    if (
        status.outcome is not FlowSessionOutcome.AUTHENTICATED
        or not isinstance(email, str)
        or not re.fullmatch(r"[^\s\"<>]{1,128}@[^\s\"<>]{1,125}", email)
        or (expected_email is not None and email.casefold() != expected_email.casefold())
    ):
        raise _reject()
    async with FlowApiClient(profile_dir=candidate, headless=False) as client:
        if project_id is None:
            snapshot = await client.list_native_projects()
            projects = snapshot.get("projects")
            if not isinstance(projects, list) or not projects:
                raise ConfigurationError(
                    detail="Imported account has no discovered Flow project",
                    remediation_hint="Create a Flow project in the hosted browser and retry.",
                )
            first = cast("list[dict[str, Any]]", projects)[0]
            project_id = str(first.get("project_id", first.get("projectId", "")))
        # Real project access is required even after the identity endpoint succeeds.
        await client.list_native_media(project_id)
    return email, project_id


async def import_cookie_profile(
    table: object,
    profile: object,
    *,
    expected_email: str | None = None,
    project_id: str | None = None,
) -> ImportedProfile:
    """Create a NEW profile only after free identity and project access checks.

    Refresh imports use a new version profile; an account mapping may switch to it
    transactionally later. No live/original profile is overwritten or declared
    authenticated from cookie presence. No output includes cookies/session tokens.
    """
    from gflow_cli.api.transports.migrated_video_upload import is_uuid
    from gflow_cli.auth import default_profile_root, profile_dir
    from gflow_cli.winsec import ensure_profile_hardened

    if not isinstance(table, CookieTable) or not 1 <= table.count <= 256:
        raise ConfigurationError(detail="A validated bounded cookie table is required")
    if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile):
        raise ConfigurationError(detail="Import profile requires a safe new profile name")
    if expected_email is not None and (
        not re.fullmatch(r"[^\s\"<>]{1,128}@[^\s\"<>]{1,125}", expected_email)
    ):
        raise ConfigurationError(detail="Expected account email is invalid")
    if project_id is not None and not is_uuid(project_id):
        raise ConfigurationError(detail="Import project identifier must be a UUID")
    home = default_profile_root().resolve()
    target = profile_dir(profile)
    if target.is_symlink() or target.exists() or target.parent.resolve() != home:
        raise ConfigurationError(detail="Cookie import requires a new profile")
    staging = home / ".cookie-staging"
    home.mkdir(parents=True, exist_ok=True)
    if staging.is_symlink():
        raise ConfigurationError(detail="Cookie staging must be a private local directory")
    staging.mkdir(mode=0o700, exist_ok=True)
    ensure_profile_hardened(staging)
    candidate: Path | None = None
    async with ProfileLease(target):
        if target.exists() or target.is_symlink():
            raise ConfigurationError(detail="Cookie import requires a new profile")
        candidate = Path(tempfile.mkdtemp(prefix="candidate-", dir=staging))
        try:
            owned_stat = candidate.stat()
            owner_identity = (owned_stat.st_dev, owned_stat.st_ino)
            ensure_profile_hardened(candidate)
            marker = candidate / ".gflow_browser_strategy"
            marker.write_text("chrome", encoding="utf-8")
            marker.chmod(0o600)
            async with asyncio.timeout(180):
                await _populate_candidate(candidate, table)
                prepare_staged_session_restore(candidate, table, owner_identity=owner_identity)
                email, selected_project = await _verify_candidate(
                    candidate, expected_email, project_id
                )
            account = candidate / ".gflow_account"
            account.write_text(email, encoding="utf-8")
            account.chmod(0o600)
            if target.exists() or target.is_symlink():
                raise ConfigurationError(detail="Import target was created concurrently")
            identity = candidate.stat()
            imported = ImportedProfile(
                profile=profile,
                email=email,
                project_id=selected_project,
                cookie_count=table.count,
                _identity=(identity.st_dev, identity.st_ino),
                _fingerprint=_fingerprint(candidate),
            )
            os.rename(candidate, target)
            candidate = None
            return imported
        except (ConfigurationError, AuthMissingError):
            raise
        except Exception:
            raise _reject() from None
        finally:
            if candidate is not None:
                original_error = sys.exc_info()[1]
                try:
                    shutil.rmtree(candidate)
                except OSError:
                    if original_error is not None:
                        original_error.add_note(
                            "Private staged import cleanup remains pending; "
                            "original profile preserved."
                        )
                    # Do not mask the original safe failure or cancellation. Keep
                    # private staging data quarantined when OS cleanup is denied.
                    structlog.get_logger(__name__).warning(
                        "auth_cookie_import_cleanup_pending",
                        cleanup_pending=True,
                        original_profile_preserved=True,
                    )


_FINGERPRINT_FILES = (
    ".gflow_account",
    ".gflow_browser_strategy",
    "Cookies",
    "Default/Cookies",
    "Default/Network/Cookies",
    "Default/Preferences",
)


def _fingerprint(path: Path) -> tuple[tuple[str, int, int, int, int], ...]:
    rows: list[tuple[str, int, int, int, int]] = []
    for name in _FINGERPRINT_FILES:
        entry = path / name
        if entry.is_symlink():
            raise ConfigurationError(detail="Imported profile state was replaced")
        try:
            stat = entry.stat()
        except FileNotFoundError:
            continue
        rows.append((name, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


async def discard_imported_profile(imported: ImportedProfile) -> bool:
    """Remove only an unchanged owned import; busy/replaced/used profiles survive."""
    from gflow_cli.auth import default_profile_root, profile_dir
    from gflow_cli.errors import ProfileLockedError

    target = profile_dir(imported.profile)
    if target.parent.resolve() != default_profile_root().resolve():
        return False
    try:
        async with ProfileLease(target):
            if not imported.matches_private_state(target):
                return False
            shutil.rmtree(target)
            return True
    except (OSError, ProfileLockedError, ConfigurationError):
        return False
