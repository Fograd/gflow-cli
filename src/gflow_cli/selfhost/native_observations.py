"""Durable URL-free observations; never ownership or absence/deletion authority."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z\Z", re.ASCII)


def _uuid(value: Any) -> str:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise ValueError("Native observation identity is invalid")
    return str(UUID(value))


def _scope(profile: str, account: str) -> None:
    if (
        not isinstance(cast(object, profile), str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile) is None
    ):
        raise ValueError("Native observation profile scope is invalid")
    if (
        not isinstance(cast(object, account), str)
        or not 1 <= len(account) <= 512
        or not account.isascii()
        or any(ord(c) < 33 or ord(c) > 126 or c in "/\\?#" for c in account)
    ):
        raise ValueError("Native observation account scope is invalid")


def _private(path: Path, directory: bool) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_mode & 0o077 or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
        raise ValueError("Native observation storage must be private and regular")


def _rows(history: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = history.get(key)
    if not isinstance(raw, list) or len(cast(list[Any], raw)) > 1000:
        raise ValueError("Native observation collection is invalid or exceeds its bound")
    result: list[dict[str, Any]] = []
    for item in cast(list[Any], raw):
        if not isinstance(item, dict):
            raise ValueError("Native observation row is invalid")
        result.append(cast(dict[str, Any], item))
    return result


def _validated(history: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(cast(object, history), dict):
        raise ValueError("Native observation snapshot is invalid")
    workflows: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    for raw in _rows(history, "workflows"):
        identifier, project = _uuid(raw.get("workflow_id")), _uuid(raw.get("project_id"))
        if identifier in owners:
            raise ValueError("Native observation workflow identity is duplicated")
        owners[identifier] = project
        row: dict[str, Any] = {"workflow_id": identifier, "project_id": project}
        if "primary_media_id" in raw:
            row["primary_media_id"] = _uuid(raw["primary_media_id"])
        if "archived" in raw:
            if type(raw["archived"]) is not bool:
                raise ValueError("Native observation archive metadata is invalid")
            row["archived"] = raw["archived"]
        workflows.append(row)
    media: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for raw in _rows(history, "media"):
        identifier, project, workflow = (
            _uuid(raw.get(k)) for k in ("media_id", "project_id", "workflow_id")
        )
        if identifier in by_id or owners.get(workflow) != project:
            raise ValueError("Native observation media ownership is ambiguous")
        kind = raw.get("kind")
        if not isinstance(kind, str) or kind not in {"image", "video", "audio", "unknown"}:
            raise ValueError("Native observation media kind is invalid")
        row = {"media_id": identifier, "project_id": project, "workflow_id": workflow, "kind": kind}
        for key in ("width", "height"):
            if key in raw:
                if (
                    kind not in {"image", "video"}
                    or type(raw[key]) is not int
                    or not 0 < raw[key] <= 100000
                ):
                    raise ValueError("Native observation dimensions are invalid")
                row[key] = raw[key]
        if ("width" in row) != ("height" in row):
            raise ValueError("Native observation dimensions must form a pair")
        if "created_time" in raw:
            stamp = raw["created_time"]
            if not isinstance(stamp, str) or _TIME.fullmatch(stamp) is None:
                raise ValueError("Native observation creation time is invalid")
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.year < 1970:
                    raise ValueError
            except ValueError:
                raise ValueError("Native observation creation time is invalid") from None
            row["created_time"] = stamp
        media.append(row)
        by_id[identifier] = row
    for row in workflows:
        primary = row.get("primary_media_id")
        if primary is not None and (
            primary not in by_id or by_id[primary]["workflow_id"] != row["workflow_id"]
        ):
            raise ValueError("Native observation primary media ownership is invalid")
    return workflows, media


class NativeObservationStore:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private(root, True)
        self.path = root / "native_observations.sqlite3"
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        _private(self.path, False)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            for table, identity in (("workflows", "workflow_id"), ("media", "media_id")):
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} (profile TEXT NOT NULL, "
                    f"account TEXT NOT NULL, {identity} TEXT NOT NULL, metadata TEXT NOT NULL, "
                    f"PRIMARY KEY(profile,account,{identity}))"
                )

    @staticmethod
    def _counts(conn: sqlite3.Connection, profile: str, account: str) -> dict[str, Any]:
        params = (profile, account)
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE profile=? AND account=?", params
            ).fetchone()[0]
            for table in ("media", "workflows")
        }
        projects = conn.execute(
            "SELECT COUNT(DISTINCT project) FROM ("
            "SELECT json_extract(metadata,'$.project_id') project FROM media "
            "WHERE profile=? AND account=? UNION "
            "SELECT json_extract(metadata,'$.project_id') project FROM workflows "
            "WHERE profile=? AND account=?)",
            params + params,
        ).fetchone()[0]
        return {
            **counts,
            "projects": projects,
            "complete": None,
            "scope": "durable observed metadata; completeness unknown",
        }

    def counts(self, profile: str, account: str) -> dict[str, Any]:
        _scope(profile, account)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN")
            return self._counts(conn, profile, account)

    def merge_history(self, profile: str, account: str, history: dict[str, Any]) -> dict[str, Any]:
        _scope(profile, account)
        workflows, media = _validated(history)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for table, identity, rows in (
                ("workflows", "workflow_id", workflows),
                ("media", "media_id", media),
            ):
                for row in rows:
                    params = (profile, account, row[identity])
                    old = conn.execute(
                        f"SELECT metadata FROM {table} WHERE profile=? AND account=? "
                        f"AND {identity}=?",
                        params,
                    ).fetchone()
                    if old is not None:
                        previous = json.loads(old[0])
                        immutable = (
                            ("project_id", "workflow_id") if table == "media" else ("project_id",)
                        )
                        if any(previous[key] != row[key] for key in immutable):
                            raise ValueError("Native observation immutable identity conflicts")
                        if (
                            table == "media"
                            and previous["kind"] != "unknown"
                            and row["kind"] != "unknown"
                            and previous["kind"] != row["kind"]
                        ):
                            raise ValueError("Native observation known media type conflicts")
                        row = {**previous, **row}
                        if table == "media" and row["kind"] not in {"image", "video"}:
                            row.pop("width", None)
                            row.pop("height", None)
                    conn.execute(
                        f"INSERT INTO {table} VALUES(?,?,?,?) "
                        f"ON CONFLICT(profile,account,{identity}) "
                        "DO UPDATE SET metadata=excluded.metadata",
                        (*params, json.dumps(row, sort_keys=True)),
                    )
            return self._counts(conn, profile, account)
