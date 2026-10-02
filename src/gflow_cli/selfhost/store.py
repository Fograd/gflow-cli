"""Private SQLite queue and managed media registry."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, cast


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "jobs.sqlite3"
        with self.connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Unsupported self-host queue schema")
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, profile TEXT NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                    updated REAL NOT NULL, result TEXT, idem TEXT UNIQUE, fingerprint TEXT);
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, profile TEXT NOT NULL, project TEXT NOT NULL,
                    path TEXT NOT NULL, mime TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS callbacks (
                    id INTEGER PRIMARY KEY, job TEXT NOT NULL, state TEXT NOT NULL,
                    url TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    due REAL NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(job,state));
                CREATE TABLE IF NOT EXISTS accounts (
                    profile TEXT PRIMARY KEY, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    project TEXT NOT NULL, enabled INTEGER NOT NULL, verified INTEGER NOT NULL);
                PRAGMA user_version=2;
            """)
        self.path.chmod(0o600)

    @contextlib.contextmanager
    def connection(self) -> Any:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _callback(
        self,
        conn: Any,
        job: str,
        state: str,
        payload: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> None:
        if not payload.get("replyUrl"):
            return
        row = conn.execute("SELECT created,updated FROM jobs WHERE id=?", (job,)).fetchone()
        message = {
            "jobId": job,
            "status": state,
            "replyRef": payload.get("replyRef"),
            "createdAt": row["created"],
            "updatedAt": row["updated"],
        }
        if result:
            message.update(result)
        conn.execute(
            "INSERT OR IGNORE INTO callbacks(job,state,url,payload,due) VALUES(?,?,?,?,?)",
            (job, state, payload["replyUrl"], json.dumps(message), time.time()),
        )

    def submit(
        self, kind: str, profile: str, payload: dict[str, Any], idem: str | None
    ) -> dict[str, Any]:
        encoded = json.dumps(payload, sort_keys=True)
        fingerprint = hashlib.sha256(f"{kind}:{profile}:{encoded}".encode()).hexdigest()
        job = str(uuid.uuid4())
        now = time.time()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = (
                conn.execute("SELECT * FROM jobs WHERE idem=?", (idem,)).fetchone()
                if idem
                else None
            )
            if existing is not None:
                if existing["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency-Key already used for a different request")
                return self.public(existing)
            if (
                conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE state IN ('created','running')"
                ).fetchone()[0]
                >= 100
            ):
                raise OverflowError("Queue is full")
            conn.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (job, kind, profile, encoded, "created", now, now, None, idem, fingerprint),
            )
            self._callback(conn, job, "created", payload)
        return self.get(job)

    def public(self, row: Any) -> dict[str, Any]:
        result = {
            "jobId": row["id"],
            "status": row["state"],
            "createdAt": row["created"],
            "updatedAt": row["updated"],
        }
        if row["result"]:
            result.update(json.loads(row["result"]))
        return result

    def by_idempotency(self, key: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE idem=?", (key,)).fetchone()
        return dict(row) if row is not None else None

    def get(self, job: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
        if row is None:
            raise KeyError(job)
        return self.public(row)

    def jobs(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [
                self.public(row)
                for row in conn.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 100")
            ]

    def claim(self, profile: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM jobs WHERE profile=? AND state='running' LIMIT 1", (profile,)
            ).fetchone():
                return None
            row = conn.execute(
                "SELECT * FROM jobs WHERE profile=? AND state='created' ORDER BY created LIMIT 1",
                (profile,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET state='running',updated=? WHERE id=?", (time.time(), row["id"])
            )
            self._callback(conn, row["id"], "started", json.loads(row["payload"]))
            return dict(row)

    def finish(self, job: str, state: str, result: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM jobs WHERE id=?", (job,)).fetchone()
            if row is None:
                raise KeyError(job)
            previous = conn.execute("SELECT result FROM jobs WHERE id=?", (job,)).fetchone()
            accumulated: dict[str, Any] = (
                json.loads(previous["result"]) if previous["result"] else {}
            )
            accumulated.update(result)
            conn.execute(
                "UPDATE jobs SET state=?,updated=?,result=? WHERE id=?",
                (state, time.time(), json.dumps(accumulated), job),
            )
            self._callback(conn, job, state, json.loads(row["payload"]), accumulated)

    def recover(self) -> None:
        with self.connection() as conn:
            rows = conn.execute("SELECT id FROM jobs WHERE state='running'").fetchall()
        for row in rows:
            self.finish(
                row["id"],
                "interrupted",
                {
                    "error": {
                        "code": "submission_outcome_unknown",
                        "retryable": False,
                        "detail": "Daemon stopped during execution. "
                        "Inspect Flow before submitting again.",
                    }
                },
            )

    def asset(self, media: str, profile: str, project: str, path: str, mime: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?)",
                (media, profile, project, path, mime),
            )

    def asset_get(self, media: str) -> dict[str, str]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id=?", (media,)).fetchone()
        if row is None:
            raise KeyError(media)
        return dict(row)

    def asset_list(self, profile: str) -> list[dict[str, str]]:
        with self.connection() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM assets WHERE profile=?", (profile,))
            ]

    def checkpoint(self, job: str, result: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE jobs SET result=?,updated=? WHERE id=? AND state='running'",
                (json.dumps(result), time.time(), job),
            )

    def account_seed(self, accounts: dict[str, dict[str, str]]) -> None:
        with self.connection() as conn:
            for profile, account in accounts.items():
                conn.execute(
                    "INSERT OR IGNORE INTO accounts VALUES(?,?,?,?,?)",
                    (profile, account["email"], account["project"], 1, 1),
                )

    def accounts(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM accounts WHERE enabled>=0 ORDER BY profile")
            ]

    def account_set(
        self, profile: str, email: str, project: str, enabled: bool, verified: bool
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO accounts VALUES(?,?,?,?,?) ON CONFLICT(profile) DO UPDATE SET "
                "email=excluded.email,project=excluded.project,enabled=excluded.enabled,verified=excluded.verified",
                (profile, email, project, int(enabled), int(verified)),
            )

    def account_delete(self, profile: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE accounts SET enabled=-1,verified=0 WHERE profile=?", (profile,))

    def profile_busy(self, profile: str) -> bool:
        with self.connection() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM jobs WHERE profile=? AND state IN ('created','running') LIMIT 1",
                    (profile,),
                ).fetchone()
                is not None
            )

    def job_page(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        profile: str | None = None,
        status: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        values: list[Any] = []
        if cursor:
            try:
                parsed = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                created, identifier = parsed["created"], parsed["id"]
                if type(created) not in (int, float) or not math.isfinite(created):
                    raise ValueError("Invalid cursor")
                uuid.UUID(identifier)
            except Exception:
                raise ValueError("Invalid cursor") from None
            clauses.append("(created<? OR (created=? AND id<?))")
            values.extend([created, created, identifier])
        for column, value in (("profile", profile), ("state", status), ("kind", kind)):
            if value is not None:
                clauses.append(f"{column}=?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs" + where + " ORDER BY created DESC,id DESC LIMIT ?",
                (*values, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more:
            last = rows[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps({"created": last["created"], "id": last["id"]}).encode()
            ).decode()
        return {"jobs": [self.public(row) for row in rows], "cursor": next_cursor}

    def asset_in_use(self, media: str) -> bool:
        def contains(value: Any) -> bool:
            if isinstance(value, str):
                return value == media
            if isinstance(value, dict):
                return any(contains(item) for item in cast(dict[str, Any], value).values())
            if isinstance(value, list):
                return any(contains(item) for item in cast(list[Any], value))
            return False

        with self.connection() as conn:
            return any(
                contains(json.loads(row["payload"]))
                for row in conn.execute(
                    "SELECT payload FROM jobs WHERE state IN ('created','running')"
                )
            )

    def asset_delete(self, media: str) -> str | None:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self.asset_in_use(media):
                raise ValueError("Asset is referenced by an active job")
            row = conn.execute("SELECT path FROM assets WHERE id=?", (media,)).fetchone()
            if row is None:
                raise KeyError(media)
            path = row["path"]
            conn.execute("DELETE FROM assets WHERE id=?", (media,))
            shared = conn.execute("SELECT 1 FROM assets WHERE path=? LIMIT 1", (path,)).fetchone()
        return None if shared or self.asset_in_use(path) else path

    def control_used(self, secret: str) -> bool:
        with self.connection() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM jobs WHERE json_extract(payload,'$.captchaSecret')=? LIMIT 1",
                    (secret,),
                ).fetchone()
                is not None
            )
