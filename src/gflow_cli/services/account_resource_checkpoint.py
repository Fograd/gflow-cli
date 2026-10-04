"""Private, epoch-scoped account resource checkpoints; never ownership authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4


def _private(path: Path, directory: bool) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_mode & 0o077 or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
        raise ValueError("Account resource storage must be private and regular")


class ResourceCheckpoint:
    """One active scan per exact profile/principal/kind; historical rows remain private."""

    def __init__(self, root: Path, profile: object, account: object, kind: str) -> None:
        if not isinstance(profile, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile) is None:
            raise ValueError("Account resource profile scope is invalid")
        if not isinstance(account, str) or not account or len(account) > 254:
            raise ValueError("Account resource principal scope is invalid")
        self.scope = (profile, hashlib.sha256(account.encode()).hexdigest(), kind)
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private(root, True)
        self.path = root / "account_resources.sqlite3"
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        _private(self.path, False)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS checkpoints(
                    profile TEXT, account TEXT, kind TEXT, version INTEGER, state TEXT,
                    PRIMARY KEY(profile,account,kind));
                CREATE TABLE IF NOT EXISTS observations(
                    profile TEXT, account TEXT, kind TEXT, identity TEXT, origin TEXT,
                    epoch TEXT, ordinal INTEGER, metadata TEXT,
                    PRIMARY KEY(profile,account,kind,identity));
            """)

    def load(self, cursor: str | None) -> tuple[int, dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT version,state FROM checkpoints WHERE profile=? AND account=? AND kind=?",
                self.scope,
            ).fetchone()
        version = row[0] if row else -1
        state: dict[str, Any]
        if cursor is not None:
            if row is None:
                raise ValueError("Account resource cursor scope is unavailable")
            state = json.loads(row[1])
            if state["token"] != cursor:
                raise ValueError("Account resource cursor is stale or belongs to another scope")
            return version, state
        state = {
            "epoch": uuid4().hex,
            "token": None,
            "native_cursor": None,
            "seen_cursors": [],
            "discovered": [],
            "pending": [],
            "read": [],
            "exhausted": False,
            "pages": 0,
            "observed_count": 0,
            "output_offset": 0,
        }
        return self.save(version, state, []), state

    def save(self, version: int, state: dict[str, Any], rows: list[dict[str, Any]]) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT version FROM checkpoints WHERE profile=? AND account=? AND kind=?",
                self.scope,
            ).fetchone()
            if (existing[0] if existing else -1) != version:
                raise ValueError("Account resource checkpoint changed concurrently")
            for row in rows:
                previous = conn.execute(
                    "SELECT origin,epoch,ordinal,metadata FROM observations "
                    "WHERE profile=? AND account=? AND kind=? AND identity=?",
                    (*self.scope, row["native_id"]),
                ).fetchone()
                if previous and previous[0] != row["origin_project_id"]:
                    raise ValueError("Account resource origin identity conflicts")
                if previous and self.scope[2] == "voice":
                    old = json.loads(previous[3])
                    if old["workflow_id"] != row["workflow_id"]:
                        raise ValueError("Account saved voice workflow identity conflicts")
                if previous and previous[1] == state["epoch"]:
                    ordinal = previous[2]
                else:
                    state["observed_count"] += 1
                    ordinal = state["observed_count"]
                if state["observed_count"] > 100000:
                    raise ValueError("Account observed resource bound exceeded")
                conn.execute(
                    "INSERT INTO observations VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT DO UPDATE SET epoch=excluded.epoch,ordinal=excluded.ordinal,"
                    "metadata=excluded.metadata",
                    (
                        *self.scope,
                        row["native_id"],
                        row["origin_project_id"],
                        state["epoch"],
                        ordinal,
                        json.dumps(row, sort_keys=True),
                    ),
                )
            conn.execute(
                "INSERT INTO checkpoints VALUES(?,?,?,?,?) ON CONFLICT DO UPDATE "
                "SET version=excluded.version,state=excluded.state",
                (*self.scope, version + 1, json.dumps(state)),
            )
        return version + 1

    def current(self) -> tuple[int, dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT version,state FROM checkpoints WHERE profile=? AND account=? AND kind=?",
                self.scope,
            ).fetchone()
        return row[0], json.loads(row[1])

    def rows(self, state: dict[str, Any], limit: int) -> list[tuple[int, dict[str, Any]]]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute(
                "SELECT ordinal,metadata FROM observations WHERE profile=? AND account=? "
                "AND kind=? AND epoch=? AND ordinal>? ORDER BY ordinal LIMIT ?",
                (*self.scope, state["epoch"], state["output_offset"], limit),
            ).fetchall()
        return [(ordinal, json.loads(metadata)) for ordinal, metadata in rows]
