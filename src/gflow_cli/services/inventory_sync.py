"""Bounded resumable native inventory; observations never grant ownership or deletion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.transports.native_voices import validate_identifier

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient

_FIELDS = {
    "projects": ("project_id",),
    "media": (
        "media_id",
        "project_id",
        "workflow_id",
        "kind",
        "width",
        "height",
        "created_time",
        "attached_to_project_id",
        "likely_upload",
        "generation_source",
    ),
    "workflows": ("workflow_id", "project_id", "primary_media_id", "archived"),
    "characters": ("entity_id", "project_id", "workflow_ids"),
    "user_voices": ("ref", "project_id", "workflow_id", "source"),
}
_IDS = {
    "projects": "project_id",
    "media": "media_id",
    "workflows": "workflow_id",
    "characters": "entity_id",
    "user_voices": "ref",
}


def validate_sync_options(max_steps: object, max_seconds: object, restart: object) -> None:
    """Reject invalid controls before profile/browser/storage access."""
    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise ValueError("max_steps requires an integer from 1 to 100")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 300:
        raise ValueError("max_seconds requires an integer from 1 to 300")
    if type(restart) is not bool:
        raise ValueError("restart requires a boolean")


def _private(path: Path, directory: bool) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_mode & 0o077 or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
        raise ValueError("Native inventory sync storage must be private and regular")


def _initial() -> dict[str, Any]:
    return {
        "project_cursor": None,
        "history_cursor": None,
        "projects_exhausted": False,
        "history_exhausted": False,
        "pending": [],
        "catalog_read": [],
        "project_cursors": [],
        "history_cursors": [],
    }


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(cast(list[Any], value)) > 1000:
        raise ValueError("Native sync collection is invalid or exceeds its bound")
    if any(not isinstance(item, dict) for item in cast(list[Any], value)):
        raise ValueError("Native sync row is invalid")
    return cast(list[dict[str, Any]], value)


def _clean(resource: str, row: dict[str, Any]) -> dict[str, Any]:
    if resource == "workflows" and "media_id" in row and "primary_media_id" not in row:
        row = {**row, "primary_media_id": row["media_id"]}
    clean: dict[str, Any] = {}
    for key in _FIELDS[resource]:
        if key not in row:
            continue
        value = row[key]
        if key.endswith("_id") or key == "ref":
            value = validate_identifier(value)
        elif key == "workflow_ids":
            if not isinstance(value, list) or len(cast(list[Any], value)) > 1000:
                raise ValueError("Native sync workflow references are invalid")
            value = [validate_identifier(item) for item in cast(list[Any], value)]
        elif key in {"width", "height"}:
            if type(value) is not int or not 0 < value <= 100000:
                raise ValueError("Native sync dimensions are invalid")
        elif key in {"archived", "likely_upload"}:
            if type(value) is not bool:
                raise ValueError("Native sync boolean metadata is invalid")
        elif key == "created_time":
            if (
                not isinstance(value, str)
                or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", value)
                is None
            ):
                raise ValueError("Native sync time metadata is invalid")
        elif key == "kind" and value not in {"image", "video", "audio", "unknown"}:
            raise ValueError("Native sync media kind is invalid")
        elif key == "generation_source" and value not in {"generated", "uploaded", "unknown"}:
            raise ValueError("Native sync generation source is invalid")
        elif key == "source" and value != "user":
            raise ValueError("Native sync saved voices require the user source")
        clean[key] = value
    if _IDS[resource] not in clean or "project_id" not in clean:
        raise ValueError("Native sync resource identity is missing")
    return clean


def _cursor(state: dict[str, Any], phase: str, snapshot: dict[str, Any]) -> None:
    value = snapshot.get("next_cursor")
    if value is not None:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 4096
            or not value.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
        ):
            raise ValueError("Native sync continuation is invalid")
        digest = hashlib.sha256(value.encode()).hexdigest()
        if digest in state[phase + "_cursors"]:
            raise ValueError("Native sync cursor cycle")
        state[phase + "_cursors"].append(digest)
    if type(snapshot.get("pagination_exhausted")) is not bool:
        raise ValueError("Native sync traversal flag is invalid")
    if snapshot["pagination_exhausted"] != (value is None):
        raise ValueError("Native sync continuation disagrees with traversal flag")
    state[phase + "_cursor"] = value
    state["projects_exhausted" if phase == "project" else "history_exhausted"] = value is None


def _schedule(state: dict[str, Any], identifiers: list[Any]) -> None:
    known = set(state["catalog_read"]) | set(state["pending"])
    for identifier in identifiers:
        project = validate_identifier(identifier)
        if project not in known:
            state["pending"].append(project)
            known.add(project)
    if len(known) > 10000:
        raise ValueError("Native sync exceeds the 10000 observed-project bound")


class _Store:
    def __init__(self, root: Path, profile: str, account: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile) is None or not account:
            raise ValueError("Native sync account/profile scope is invalid")
        self.profile = profile
        self.account = hashlib.sha256(account.encode()).hexdigest()
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        _private(root, True)
        self.path = root / "native_inventory_sync.sqlite3"
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        _private(self.path, False)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints (profile TEXT, account TEXT, "
                "version INTEGER, state TEXT, PRIMARY KEY(profile,account))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS observations (profile TEXT, account TEXT, "
                "scope TEXT, resource TEXT, project TEXT, identity TEXT, metadata TEXT, "
                "PRIMARY KEY(profile,account,scope,resource,project,identity))"
            )

    def load(self) -> tuple[int, dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT version,state FROM checkpoints WHERE profile=? AND account=?",
                (self.profile, self.account),
            ).fetchone()
        return (-1, _initial()) if row is None else (row[0], json.loads(row[1]))

    def save(
        self,
        version: int,
        state: dict[str, Any],
        observations: list[tuple[str, str, dict[str, Any]]],
    ) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT version FROM checkpoints WHERE profile=? AND account=?",
                (self.profile, self.account),
            ).fetchone()
            current = -1 if row is None else row[0]
            if current != version:
                raise ValueError("Native sync checkpoint changed concurrently; resume again")
            for scope, resource, raw in observations:
                clean = _clean(resource, raw)
                identity = clean[_IDS[resource]]
                key = (self.profile, self.account, scope, resource, clean["project_id"], identity)
                old = conn.execute(
                    "SELECT metadata FROM observations WHERE profile=? AND account=? "
                    "AND scope=? AND resource=? AND identity=?",
                    (self.profile, self.account, scope, resource, identity),
                ).fetchone()
                if old is not None:
                    previous = json.loads(old[0])
                    if previous["project_id"] != clean["project_id"]:
                        raise ValueError("Native sync resource origin project identity conflicts")
                    if resource == "media":
                        previous_kind = previous.get("kind", "unknown")
                        kind = clean.get("kind", "unknown")
                        if (
                            previous_kind != "unknown"
                            and kind != "unknown"
                            and kind != previous_kind
                        ):
                            raise ValueError("Native sync known media kind conflicts")
                        if kind == "unknown" and previous_kind != "unknown":
                            clean["kind"] = previous_kind
                    if (
                        "workflow_id" in previous
                        and "workflow_id" in clean
                        and previous["workflow_id"] != clean["workflow_id"]
                    ):
                        raise ValueError("Native sync resource workflow identity conflicts")
                    clean = {**previous, **clean}
                conn.execute(
                    "INSERT INTO observations VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT DO UPDATE SET metadata=excluded.metadata",
                    (*key, json.dumps(clean, sort_keys=True)),
                )
            conn.execute(
                "INSERT INTO checkpoints VALUES(?,?,?,?) ON CONFLICT DO UPDATE "
                "SET version=excluded.version,state=excluded.state",
                (self.profile, self.account, version + 1, json.dumps(state)),
            )
        return version + 1

    def counts(self) -> dict[str, Any]:
        result = {
            scope: dict.fromkeys(_FIELDS, 0)
            for scope in ("discovery", "project_catalog", "native_history")
        }
        with closing(sqlite3.connect(self.path)) as conn:
            for scope, resource, count in conn.execute(
                "SELECT scope,resource,count(*) FROM observations WHERE profile=? AND account=? "
                "GROUP BY scope,resource",
                (self.profile, self.account),
            ):
                result[scope][resource] = count
        return result


async def sync_native_inventory(
    client: FlowApiClient,
    root: Path,
    *,
    profile: str,
    account: str,
    max_steps: int = 10,
    max_seconds: int = 180,
    restart: bool = False,
) -> dict[str, Any]:
    """Commit one read at a time; cap/time interruption retains the last checkpoint.

    Account is the caller's configured/verified account identity, not a discovered display name.
    Pagination cursors live only in the private checkpoint, never the output or observations.
    Metadata is partitioned by discovery/project catalog/history scope. Attached media keeps
    its origin project and explicit attachment relationship; completeness is always unknown.
    """
    validate_sync_options(max_steps, max_seconds, restart)
    store = _Store(root, profile, account)
    version, state = store.load()
    if restart:
        state = _initial()
        version = store.save(version, state, [])
    steps = 0
    timed_out = False
    try:
        async with asyncio.timeout(max_seconds):
            for _ in range(max_steps):
                observations: list[tuple[str, str, dict[str, Any]]] = []
                if state["pending"]:
                    project = state["pending"][0]
                    result = await client.list_native_projects(
                        include_catalogs=True, catalog_project_ids=[project], max_projects=1
                    )
                    catalogs = _rows(result.get("project_catalogs"))
                    if len(catalogs) != 1 or catalogs[0].get("project_id") != project:
                        raise ValueError("Native sync catalog request project is inconsistent")
                    catalog = catalogs[0]
                    observations.append(("project_catalog", "projects", {"project_id": project}))
                    for resource in ("media", "workflows", "characters", "user_voices"):
                        for row in _rows(catalog.get(resource)):
                            if resource != "media" and row.get("project_id") != project:
                                raise ValueError("Native sync catalog has unrelated project scope")
                            if resource == "media" and row.get("project_id") != project:
                                if row.get("attached_to_project_id") != project:
                                    raise ValueError(
                                        "Native sync media attachment scope is invalid"
                                    )
                            observations.append(("project_catalog", resource, row))
                    state["pending"].pop(0)
                    state["catalog_read"].append(project)
                elif not state["projects_exhausted"]:
                    result = await client.list_native_projects(cursor=state["project_cursor"])
                    projects = _rows(result.get("projects"))
                    _schedule(state, [row.get("project_id") for row in projects])
                    _cursor(state, "project", result)
                    observations.extend(("discovery", "projects", row) for row in projects)
                elif not state["history_exhausted"]:
                    result = await client.list_native_history(cursor=state["history_cursor"])
                    if result.get("pages_read") == 0:
                        break
                    _cursor(state, "history", result)
                    for resource in ("workflows", "media"):
                        rows = _rows(result.get(resource))
                        _schedule(state, [row.get("project_id") for row in rows])
                        observations.extend(("native_history", resource, row) for row in rows)
                else:
                    break
                version = store.save(version, state, observations)
                steps += 1
    except TimeoutError:
        timed_out = True
    # Reload: mutations made by an interrupted/uncommitted step must not escape in output.
    _, state = store.load()
    finished = bool(
        state["projects_exhausted"] and state["history_exhausted"] and not state["pending"]
    )
    return {
        "steps_read": steps,
        "timed_out": timed_out,
        "traversal_finished": finished,
        "pending_project_count": len(state["pending"]),
        "catalog_projects_read": len(state["catalog_read"]),
        "project_pagination_exhausted": state["projects_exhausted"],
        "history_pagination_exhausted": state["history_exhausted"],
        "complete": None,
        "scope": "durable observed native inventory; completeness unknown; no deletion authority",
        "resource_scopes": {
            name: {"scope": scope, "complete": None}
            for name, scope in {
                "projects": "account project discovery and observed project catalogs",
                "media": "project catalogs with explicit attachments and bounded native history",
                "workflows": "project catalogs and bounded native account history",
                "characters": "observed project catalogs",
                "user_voices": "observed saved user voices",
            }.items()
        },
        "observations": store.counts(),
    }
