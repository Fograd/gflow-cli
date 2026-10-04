"""Bounded carryforward of confirmed receipts into a verified replacement profile."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from gflow_cli.api.native_delete_receipts import DeleteReceipts
from gflow_cli.api.transports.native_voices import validate_identifier

MAX_RECEIPT_PROJECTS = 1000
MAX_RECEIPT_FILES = 10000


def _private_directory(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_mode & 0o077
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        raise ValueError("Confirmed delete receipt directory is not private and regular")


def carry_delete_receipts(original: Path, candidate: Path, verified_email: str) -> int:
    """Copy only fixed validated receipt metadata while both profile leases are held.

    The caller has freshly verified the candidate identity and confirmed that the original
    marker matches it. Receipt metadata is prior acknowledgment, never fresh ownership proof.
    Google deletion still verifies the current principal/project and exact NOT_FOUND outcome.
    An activation failure discards the candidate; the original is never modified.
    """
    try:
        return _carry_delete_receipts(original, candidate, verified_email)
    except OSError:
        raise ValueError("Confirmed delete receipt storage is unavailable or unsafe") from None


def _carry_delete_receipts(original: Path, candidate: Path, verified_email: str) -> int:
    if original.is_symlink() or not original.is_dir():
        raise ValueError("Confirmed delete receipt source profile is invalid")
    _private_directory(candidate)
    owner = hashlib.sha256(verified_email.casefold().encode("utf-8")).hexdigest()
    base = original / ".gflow_delete_receipts"
    if not base.exists() and not base.is_symlink():
        return 0
    _private_directory(base)
    source = base / owner
    if not source.exists() and not source.is_symlink():
        return 0
    _private_directory(source)
    rows: list[tuple[str, str, str]] = []
    files = 0
    for index, folder in enumerate(source.iterdir(), 1):
        if index > MAX_RECEIPT_PROJECTS:
            raise ValueError("Confirmed delete receipts exceed the project bound")
        project = validate_identifier(folder.name)
        if project != folder.name:
            raise ValueError("Confirmed delete receipt project identity is invalid")
        _private_directory(folder)
        receipts = DeleteReceipts(original, owner, project)
        for target in folder.iterdir():
            files += 1
            if files > MAX_RECEIPT_FILES:
                raise ValueError("Confirmed delete receipts exceed the file bound")
            if target.name.startswith(".pending-"):
                continue
            if target.suffix != ".json":
                raise ValueError("Confirmed delete receipt file identity is invalid")
            identifier = validate_identifier(target.stem)
            if identifier != target.stem:
                raise ValueError("Confirmed delete receipt media identity is invalid")
            kind = receipts.kind(identifier)
            if kind is None:
                raise ValueError("Confirmed delete receipt disappeared during refresh")
            rows.append((project, identifier, kind))
    # Preflight the entire batch before writing any receipt files to the candidate.
    destinations: dict[str, DeleteReceipts] = {}
    for project, identifier, kind in rows:
        if project not in destinations:
            destinations[project] = DeleteReceipts(candidate, owner, project)
        current = destinations[project].kind(identifier)
        if current is not None and current != kind:
            raise ValueError("Confirmed delete receipt kind conflicts in the candidate")
    for project, identifier, kind in rows:
        destinations[project].record(identifier, kind)
    return len(rows)
