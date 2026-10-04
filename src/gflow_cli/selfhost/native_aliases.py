"""Private exact composite aliases; Google ownership is verified by the caller."""

from __future__ import annotations

import os
import re
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

_ALIAS = re.compile(
    r"user:([A-Za-z0-9._~-]{1,128})-email:([A-Za-z0-9._~-]{1,512})-"
    r"(image|video):([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\Z"
)


def alias_spec(alias: str) -> tuple[Literal["image", "video"], str]:
    """Validate syntax only; opaque prefixes never establish account ownership."""
    if not isinstance(cast(object, alias), str) or len(alias) > 1024 or not alias.isascii():
        raise ValueError("Native composite alias has an invalid shape")
    match = _ALIAS.fullmatch(alias)
    if match is None:
        raise ValueError("Native composite alias has an invalid shape")
    kind: Literal["image", "video"] = "image" if match[3] == "image" else "video"
    return kind, str(UUID(match[4]))


@dataclass(frozen=True)
class NativeAlias:
    alias: str = field(repr=False)
    profile: str
    account: str = field(repr=False)
    project_id: str
    media_id: str
    kind: Literal["image", "video"]


def _scope(profile: str, account: str) -> None:
    if (
        not isinstance(cast(object, profile), str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile) is None
    ):
        raise ValueError("Native alias profile scope is invalid")
    if (
        not isinstance(cast(object, account), str)
        or not 1 <= len(account) <= 512
        or not account.isascii()
        or any(ord(c) < 33 or ord(c) > 126 or c in "/\\?#" for c in account)
    ):
        raise ValueError("Native alias account scope is invalid")


def _canonical_uuid(value: str) -> str:
    if (
        not isinstance(cast(object, value), str)
        or re.fullmatch(
            r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", value
        )
        is None
    ):
        raise ValueError("Native alias identity is invalid")
    return str(UUID(value))


def _validated(binding: NativeAlias) -> NativeAlias:
    if not isinstance(cast(object, binding), NativeAlias):
        raise ValueError("Native alias binding is invalid")
    kind, media = alias_spec(binding.alias)
    _scope(binding.profile, binding.account)
    project = _canonical_uuid(binding.project_id)
    if binding.kind != kind or _canonical_uuid(binding.media_id) != media:
        raise ValueError("Native alias suffix does not match its binding")
    return NativeAlias(binding.alias, binding.profile, binding.account, project, media, kind)


def _private(path: Path, *, directory: bool) -> None:
    info = path.lstat()
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or info.st_mode & 0o077:
        raise ValueError("Native alias storage must be private and regular")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("Native alias storage has another owner")


class NativeAliasStore:
    def __init__(
        self, root: Path, *, resolve_scope: Callable[[str, str], str | None] | None = None
    ) -> None:
        self.resolve_scope = resolve_scope
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private(root, directory=True)
        self.path = root / "aliases.sqlite3"
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        _private(self.path, directory=False)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, "
                "profile TEXT NOT NULL, "
                "account TEXT NOT NULL, project_id TEXT NOT NULL, media_id TEXT NOT NULL, "
                "kind TEXT NOT NULL CHECK(kind IN ('image','video')))"
            )

    def _resolved(self, binding: NativeAlias) -> NativeAlias:
        if self.resolve_scope is None:
            return binding
        profile = self.resolve_scope(binding.profile, binding.account)
        return binding if profile is None else _validated(replace(binding, profile=profile))

    def register(self, binding: NativeAlias) -> None:
        item = _validated(binding)
        values = (item.alias, item.profile, item.account, item.project_id, item.media_id, item.kind)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?,?)", values)
            stored = conn.execute("SELECT * FROM aliases WHERE alias=?", (item.alias,)).fetchone()
            if self._resolved(_validated(NativeAlias(*stored))) != item:
                raise ValueError("Native alias conflicts with an existing binding")

    def get(self, alias: str) -> NativeAlias | None:
        alias_spec(alias)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            row = conn.execute("SELECT * FROM aliases WHERE alias=?", (alias,)).fetchone()
        if row is None:
            return None
        return self._resolved(_validated(NativeAlias(*row)))

    def remove(self, alias: str, profile: str, account: str) -> bool:
        alias_spec(alias)
        _scope(profile, account)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT profile,account FROM aliases WHERE alias=?", (alias,)
            ).fetchone()
            if row is None:
                return False
            stored_profile, stored_account = row
            resolved = (
                self.resolve_scope(stored_profile, stored_account)
                if self.resolve_scope is not None
                else stored_profile
            )
            if (resolved, stored_account) != (profile, account):
                raise ValueError("Native alias belongs to another scope")
            conn.execute("DELETE FROM aliases WHERE alias=?", (alias,))
            return True
