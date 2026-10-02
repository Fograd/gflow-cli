"""Private SQLite queue and managed media registry."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "jobs.sqlite3"
        with self.connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
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
                PRAGMA user_version=1;
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
            conn.execute(
                "UPDATE jobs SET state=?,updated=?,result=? WHERE id=?",
                (state, time.time(), json.dumps(result), job),
            )
            self._callback(conn, job, state, json.loads(row["payload"]), result)

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
