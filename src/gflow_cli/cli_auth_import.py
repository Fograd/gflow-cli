"""Credential-file import adapter; cookie values never become CLI arguments/output."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import click
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import run_with_handlers
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.profile_import import import_cookie_profile
from gflow_cli.selfhost.session_import import MAX_TABLE_BYTES, CookieTableError, parse_cookie_table

console = Console()


def _read_table(path: Path) -> str:
    fd: int | None = None
    try:
        existing = path.lstat()
        if not stat.S_ISREG(existing.st_mode) or existing.st_size > MAX_TABLE_BYTES:
            raise ValueError
        fd = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0),
        )
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > MAX_TABLE_BYTES
            or (existing.st_dev, existing.st_ino, existing.st_size, existing.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            raise ValueError
        data = bytearray()
        while len(data) <= MAX_TABLE_BYTES:
            chunk = os.read(fd, min(65536, MAX_TABLE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        if (
            len(data) > MAX_TABLE_BYTES
            or path.is_symlink()
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise ValueError
        return data.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError(
            detail="Cookie input requires an unchanged regular UTF-8 file of at most 1 MiB"
        ) from None
    finally:
        if fd is not None:
            os.close(fd)


async def _import(
    cookies_file: Path,
    profile: str,
    expected_email: str | None,
    project_id: str | None,
    as_json: bool,
) -> None:
    try:
        table = parse_cookie_table(_read_table(cookies_file))
    except CookieTableError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    result = await import_cookie_profile(
        table, profile, expected_email=expected_email, project_id=project_id
    )
    payload = {
        "profile": result.profile,
        "email": result.email,
        "projectId": result.project_id,
        "cookieCount": result.cookie_count,
        "verificationSource": "live Google identity and Flow project access",
        "scope": result.scope,
    }
    if as_json:
        json_output.emit(payload)
    else:
        console.print(f"Imported verified profile {result.profile}.", markup=False)
        console.print(
            "Register it through the account API for self-hosted jobs, "
            "or select it with gflow auth use.",
            markup=False,
        )


@click.command("import-cookies")
@click.option(
    "--cookies-file",
    required=True,
    type=click.Path(path_type=Path),
    help="Private UTF-8 DevTools TSV cookie file, at most 1 MiB.",
)
@click.option("--profile", required=True, help="New profile name; existing profiles are preserved.")
@click.option("--expected-email", default=None, help="Require this actual Google account identity.")
@click.option("--project", "project_id", default=None, help="Require access to this project UUID.")
@click.option("--json", "as_json", is_flag=True, help="Emit safe profile metadata.")
def import_cookies(
    cookies_file: Path,
    profile: str,
    expected_email: str | None,
    project_id: str | None,
    as_json: bool,
) -> None:
    """Import and verify cookies into a new headed Chrome profile, without generation."""
    run_with_handlers(
        lambda: _import(cookies_file, profile, expected_email, project_id, as_json),
        cli_command="auth import-cookies",
        as_json=as_json,
    )
