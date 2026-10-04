"""Bounded observed account characters/saved voices; unknown global completeness."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.services.account_resource_checkpoint import ResourceCheckpoint

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient

ResourceKind = Literal["character", "voice"]
RESULT_LIMIT = 1000

_expected_account_sha256: ContextVar[str | None] = ContextVar(
    "account_resource_expected_principal", default=None
)


@contextmanager
def bind_account_resource_identity(expected: object) -> Generator[None, None, None]:
    """Bind a private worker dispatch to one exact principal; never expose its digest."""
    from gflow_cli.errors import ConfigurationError

    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ConfigurationError(detail="Account resource dispatch identity is unavailable")
    token = _expected_account_sha256.set(expected)
    try:
        yield
    finally:
        _expected_account_sha256.reset(token)


def validate_account_resource_options(
    kind: object, cursor: object, max_projects: object, max_pages: object, max_seconds: object
) -> None:
    if kind not in ("character", "voice"):
        raise ValueError("kind requires character or voice")
    for name, value, maximum in (
        ("max_projects", max_projects, 20),
        ("max_pages", max_pages, 100),
        ("max_seconds", max_seconds, 180),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{name} requires an integer from 1 to {maximum}")
    if cursor is not None and (
        not isinstance(cursor, str) or re.fullmatch(r"[0-9a-f]{32}", cursor) is None
    ):
        raise ValueError("Account resource cursor must be an opaque continuation")


def _rows(value: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or len(cast(list[Any], value)) > 1000
        or any(not isinstance(row, dict) for row in cast(list[Any], value))
    ):
        raise ValueError("Account resource collection exceeds its valid bound")
    return cast(list[dict[str, Any]], value)


def _resource_rows(
    catalog: dict[str, Any], project: str, kind: ResourceKind
) -> list[dict[str, Any]]:
    rows = _rows(catalog.get("characters" if kind == "character" else "user_voices"))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        origin = validate_identifier(row.get("project_id"))
        if origin != project:
            raise ValueError("Account resource has an unrelated catalog origin")
        identifier = validate_identifier(row.get("entity_id" if kind == "character" else "ref"))
        if identifier in seen:
            raise ValueError("Account resource identity is duplicated in a catalog")
        seen.add(identifier)
        clean: dict[str, Any] = {
            "kind": kind,
            "native_id": identifier,
            "origin_project_id": origin,
            "observed_in_project_ids": [project],
        }
        if kind == "character":
            workflows = row.get("workflow_ids")
            if not isinstance(workflows, list) or len(cast(list[Any], workflows)) > 1000:
                raise ValueError("Character workflow references are unavailable")
            clean["workflow_ids"] = list(
                dict.fromkeys(validate_identifier(item) for item in cast(list[Any], workflows))
            )
        else:
            if row.get("source") != "user":
                raise ValueError("Account saved voice must have the user source")
            clean["workflow_id"] = validate_identifier(row.get("workflow_id"))
        result.append(clean)
    return result


def _discovery(state: dict[str, Any], snapshot: dict[str, Any]) -> None:
    rows = _rows(snapshot.get("projects"))
    identifiers = [validate_identifier(row.get("project_id")) for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate account discovery project identity")
    known = set(state["discovered"])
    for project in identifiers:
        if project not in known:
            state["discovered"].append(project)
            state["pending"].append(project)
            known.add(project)
    if len(known) > 10000:
        raise ValueError("Account observed project bound exceeded")
    cursor = snapshot.get("next_cursor")
    if cursor is not None:
        if (
            not isinstance(cursor, str)
            or not 1 <= len(cursor) <= 4096
            or not cursor.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in cursor)
        ):
            raise ValueError("Native account project continuation is invalid")
        digest = hashlib.sha256(cursor.encode()).hexdigest()
        if digest in state["seen_cursors"]:
            raise ValueError("Account project cursor cycle")
        state["seen_cursors"].append(digest)
    if type(snapshot.get("pagination_exhausted")) is not bool or (
        snapshot["pagination_exhausted"] != (cursor is None)
    ):
        raise ValueError("Account project traversal flag is inconsistent")
    state["native_cursor"] = cursor
    state["exhausted"] = cursor is None
    state["pages"] += 1


def account_resource_scope(client: FlowApiClient) -> tuple[Path, str, str]:
    """Derive one bounded principal from a current marker in the configured private home."""
    import os
    import stat

    from gflow_cli.errors import ConfigurationError
    from gflow_cli.profile_store import read_account_file

    try:
        home = client.settings.home.resolve()
        profile = client.profile_dir.name.removeprefix("profile_")
        location = client.profile_dir.resolve(strict=True)
        location.relative_to(home)
        if location != client.settings.profile_subdir(profile).resolve():
            raise ValueError()
        marker = location / ".gflow_account"
        info = marker.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_size > 254
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
        ):
            raise ValueError()
        account = read_account_file(location)
        if account is None or re.fullmatch(r'[^\s"<>]{1,128}@[^\s"<>]{1,125}', account) is None:
            raise ValueError()
    except (OSError, ValueError):
        raise ConfigurationError(
            detail="Account resources require a current private identity marker"
        ) from None
    expected = _expected_account_sha256.get()
    if expected is not None and hashlib.sha256(account.encode()).hexdigest() != expected:
        raise ConfigurationError(detail="Account resource dispatch identity changed")
    return home / "native_inventory", profile, account


async def list_account_resources(
    client: FlowApiClient,
    root: Path,
    *,
    profile: str,
    account: str,
    kind: ResourceKind,
    cursor: str | None = None,
    max_projects: int = 10,
    max_pages: int = 1,
    max_seconds: int = 180,
    verify_scope: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """A new call starts a fresh epoch; an opaque cursor resumes committed progress.

    Only fresh catalog observations in this epoch are returned. Previous rows survive
    privately and never authorize absence deletion. Google cursors stay in private state.
    A continuation drains pending committed result rows before making further native reads.
    """
    validate_account_resource_options(kind, cursor, max_projects, max_pages, max_seconds)
    if verify_scope is not None:
        verify_scope()
    store = ResourceCheckpoint(root, profile, account, kind)
    version, state = store.load(cursor)
    pages = projects = 0
    timed_out = False
    if state["observed_count"] == state["output_offset"]:
        try:
            async with asyncio.timeout(max_seconds):
                while True:
                    if verify_scope is not None:
                        verify_scope()
                    if state["pending"] and projects < max_projects:
                        project = state["pending"][0]
                        snapshot = await client.list_native_projects(
                            include_catalogs=True, catalog_project_ids=[project], max_projects=1
                        )
                        catalogs = _rows(snapshot.get("project_catalogs"))
                        if len(catalogs) != 1 or catalogs[0].get("project_id") != project:
                            raise ValueError("Account catalog request project is inconsistent")
                        rows = _resource_rows(catalogs[0], project, kind)
                        state["pending"].pop(0)
                        state["read"].append(project)
                        if verify_scope is not None:
                            verify_scope()
                        version = store.save(version, state, rows)
                        projects += 1
                    elif not state["exhausted"] and pages < max_pages:
                        snapshot = await client.list_native_projects(cursor=state["native_cursor"])
                        _discovery(state, snapshot)
                        if verify_scope is not None:
                            verify_scope()
                        version = store.save(version, state, [])
                        pages += 1
                    else:
                        break
        except TimeoutError:
            timed_out = True
    # Never publish changes from an interrupted/uncommitted read.
    # The token stays valid across partial reads; only a published continuation advances it.
    current_version, state = store.current()
    if current_version != version:
        raise ValueError("Account resource checkpoint changed concurrently")
    records = store.rows(state, RESULT_LIMIT)
    if records:
        state["output_offset"] = records[-1][0]
    pending_results = state["observed_count"] - state["output_offset"]
    finished = state["exhausted"] and not state["pending"]
    state["token"] = uuid4().hex if pending_results or not finished else None
    if verify_scope is not None:
        verify_scope()
    store.save(version, state, [])
    return {
        "resources": [resource for _, resource in records],
        "kind": kind,
        "returned_count": len(records),
        "observed_count": state["observed_count"],
        "next_cursor": state["token"],
        "pending_result_count": pending_results,
        "pending_project_count": len(state["pending"]),
        "pages_read": pages,
        "catalog_projects_read": projects,
        "total_pages_read": state["pages"],
        "total_catalog_projects_read": len(state["read"]),
        "cursor_count": len(state["seen_cursors"]),
        "project_pagination_exhausted": state["exhausted"],
        "traversal_finished": finished,
        "timed_out": timed_out,
        "truncated": state["token"] is not None,
        "complete": None,
        "deletion_authority": False,
        "scope": "observed account project catalogs; completeness unknown",
    }
