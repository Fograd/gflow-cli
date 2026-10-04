"""Private resource mappings require independent fresh Google ownership proof."""

from __future__ import annotations

import os
import re
import sqlite3
import stat
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

_PREFIX = r"user:[A-Za-z0-9._~-]{1,128}-email:[A-Za-z0-9._~-]{1,512}-"
_UUID = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
_CHARACTER = re.compile(
    _PREFIX + r"character:(" + _UUID + r")-imgs:([12])(?:-voice:(" + _UUID + r"))?\Z"
)
_VOICE = re.compile(_PREFIX + r"voice:(" + _UUID + r")-mid:(" + _UUID + r")\Z")


@dataclass(frozen=True)
class ResourceAliasSpec:
    kind: Literal["character", "voice"]
    native_id: str
    workflow_id: str | None = None
    image_count: int | None = None
    voice_workflow_id: str | None = None


def resource_alias_spec(alias: str) -> ResourceAliasSpec:
    if not isinstance(cast(object, alias), str) or len(alias) > 1024 or not alias.isascii():
        raise ValueError("Native resource alias has an invalid shape")
    character = _CHARACTER.fullmatch(alias)
    if character is not None:
        return ResourceAliasSpec(
            "character",
            str(UUID(character[1])),
            image_count=int(character[2]),
            voice_workflow_id=str(UUID(character[3])) if character[3] else None,
        )
    voice = _VOICE.fullmatch(alias)
    if voice is not None:
        return ResourceAliasSpec("voice", str(UUID(voice[2])), workflow_id=str(UUID(voice[1])))
    raise ValueError("Native resource alias has an invalid shape")


@dataclass(frozen=True)
class NativeResourceAlias:
    alias: str = field(repr=False)
    profile: str
    account: str = field(repr=False)
    project_id: str
    kind: Literal["character", "voice"]
    native_id: str
    workflow_id: str | None = None
    image_count: int | None = None
    voice_workflow_id: str | None = None


def _scope(profile: str, account: str) -> None:
    if (
        not isinstance(cast(object, profile), str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile) is None
    ):
        raise ValueError("Native resource alias profile scope is invalid")
    if (
        not isinstance(cast(object, account), str)
        or not 1 <= len(account) <= 512
        or not account.isascii()
        or any(ord(c) < 33 or ord(c) > 126 or c in "/\\?#" for c in account)
    ):
        raise ValueError("Native resource alias account scope is invalid")


def _canonical_uuid(value: str) -> str:
    if (
        not isinstance(cast(object, value), str)
        or re.fullmatch(
            r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", value
        )
        is None
    ):
        raise ValueError("Native resource alias identity is invalid")
    return str(UUID(value))


def _validated(binding: NativeResourceAlias) -> NativeResourceAlias:
    if not isinstance(cast(object, binding), NativeResourceAlias):
        raise ValueError("Native resource alias binding is invalid")
    spec = resource_alias_spec(binding.alias)
    _scope(binding.profile, binding.account)
    project = _canonical_uuid(binding.project_id)
    native = _canonical_uuid(binding.native_id)
    workflow = _canonical_uuid(binding.workflow_id) if binding.workflow_id is not None else None
    voice_workflow = (
        _canonical_uuid(binding.voice_workflow_id)
        if binding.voice_workflow_id is not None
        else None
    )
    if (
        binding.kind != spec.kind
        or native != spec.native_id
        or workflow != spec.workflow_id
        or voice_workflow != spec.voice_workflow_id
        or binding.image_count != spec.image_count
        or (binding.image_count is not None and type(binding.image_count) is not int)
    ):
        raise ValueError("Native resource alias suffix does not match its binding")
    return NativeResourceAlias(
        binding.alias,
        binding.profile,
        binding.account,
        project,
        spec.kind,
        native,
        workflow,
        spec.image_count,
        voice_workflow,
    )


def _private(path: Path, *, directory: bool) -> None:
    info = path.lstat()
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or info.st_mode & 0o077:
        raise ValueError("Native resource alias storage must be private and regular")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("Native resource alias storage has another owner")


class NativeResourceAliasStore:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private(root, directory=True)
        self.path = root / "resource_aliases.sqlite3"
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
                "account TEXT NOT NULL, project_id TEXT NOT NULL, kind TEXT NOT NULL, "
                "native_id TEXT NOT NULL, workflow_id TEXT, image_count INTEGER, "
                "voice_workflow_id TEXT)"
            )

    def register(self, binding: NativeResourceAlias) -> None:
        item = _validated(binding)
        values = (
            item.alias,
            item.profile,
            item.account,
            item.project_id,
            item.kind,
            item.native_id,
            item.workflow_id,
            item.image_count,
            item.voice_workflow_id,
        )
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?,?,?,?,?)", values)
            stored = conn.execute("SELECT * FROM aliases WHERE alias=?", (item.alias,)).fetchone()
            if stored != values:
                raise ValueError("Native resource alias conflicts with an existing binding")

    def get(self, alias: str) -> NativeResourceAlias | None:
        resource_alias_spec(alias)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            row = conn.execute("SELECT * FROM aliases WHERE alias=?", (alias,)).fetchone()
        if row is None:
            return None
        return _validated(NativeResourceAlias(*row))

    def remove(self, alias: str, profile: str, account: str) -> bool:
        resource_alias_spec(alias)
        _scope(profile, account)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT profile,account FROM aliases WHERE alias=?", (alias,)
            ).fetchone()
            if row is None:
                return False
            if row != (profile, account):
                raise ValueError("Native resource alias belongs to another scope")
            conn.execute("DELETE FROM aliases WHERE alias=?", (alias,))
            return True
