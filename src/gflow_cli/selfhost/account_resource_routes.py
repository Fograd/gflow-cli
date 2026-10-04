"""Authenticated bounded account resource listing; observations are not deletion authority."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request

from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.selfhost.runtime import parse_json_output

_SCOPE = "observed account project catalogs; completeness unknown"
_COUNTERS = (
    "returned_count",
    "observed_count",
    "pending_result_count",
    "pending_project_count",
    "pages_read",
    "catalog_projects_read",
    "total_pages_read",
    "total_catalog_projects_read",
    "cursor_count",
)
_FLAGS = ("project_pagination_exhausted", "traversal_finished", "timed_out", "truncated")


def public_result(
    value: dict[str, Any], kind: str, max_projects: int, max_pages: int
) -> dict[str, Any]:
    """Validate the private worker envelope and publish only documented fields."""
    if (
        value.get("status") != "ok"
        or value.get("kind") != kind
        or "complete" not in value
        or value["complete"] is not None
        or value.get("deletion_authority") is not False
        or value.get("scope") != _SCOPE
    ):
        raise ValueError("Untrusted account resource scope")
    counters = {}
    for name in _COUNTERS:
        number = value.get(name)
        if type(number) is not int or not 0 <= number <= 100000:
            raise ValueError("Untrusted account resource counter")
        counters[name] = number
    flags = {}
    for name in _FLAGS:
        flag = value.get(name)
        if type(flag) is not bool:
            raise ValueError("Untrusted account resource flag")
        flags[name] = flag
    cursor = value.get("next_cursor")
    if cursor is not None and (
        not isinstance(cursor, str) or re.fullmatch(r"[0-9a-f]{32}", cursor) is None
    ):
        raise ValueError("Untrusted account resource continuation")
    if (
        "next_cursor" not in value
        or flags["truncated"] != (cursor is not None)
        or counters["pages_read"] > max_pages
        or counters["catalog_projects_read"] > max_projects
        or counters["pages_read"] > counters["total_pages_read"]
        or counters["catalog_projects_read"] > counters["total_catalog_projects_read"]
        or counters["pending_project_count"] > 10000
        or counters["total_catalog_projects_read"] > 10000
        or counters["returned_count"] > 1000
        or counters["returned_count"] + counters["pending_result_count"]
        > counters["observed_count"]
        or flags["traversal_finished"]
        != (flags["project_pagination_exhausted"] and counters["pending_project_count"] == 0)
        or (
            cursor is None and (not flags["traversal_finished"] or counters["pending_result_count"])
        )
    ):
        raise ValueError("Inconsistent account resource continuation")
    rows = value.get("resources")
    if not isinstance(rows, list) or len(cast(list[Any], rows)) != counters["returned_count"]:
        raise ValueError("Untrusted account resource rows")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in cast(list[Any], rows):
        if not isinstance(raw, dict) or cast(dict[str, Any], raw).get("kind") != kind:
            raise ValueError("Untrusted account resource kind")
        row = cast(dict[str, Any], raw)
        identifier = validate_identifier(row.get("native_id"))
        origin = validate_identifier(row.get("origin_project_id"))
        observed = row.get("observed_in_project_ids")
        if observed != [origin] or identifier in seen:
            raise ValueError("Untrusted account resource identity")
        seen.add(identifier)
        clean: dict[str, Any] = {
            "kind": kind,
            "native_id": identifier,
            "origin_project_id": origin,
            "observed_in_project_ids": [origin],
        }
        if kind == "voice":
            clean["workflow_id"] = validate_identifier(row.get("workflow_id"))
        else:
            workflows = row.get("workflow_ids")
            if not isinstance(workflows, list) or len(cast(list[Any], workflows)) > 1000:
                raise ValueError("Untrusted character workflow collection")
            ids = [validate_identifier(item) for item in cast(list[Any], workflows)]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate character workflow")
            clean["workflow_ids"] = ids
        cleaned.append(clean)
    return {
        "resources": cleaned,
        "kind": kind,
        **counters,
        **flags,
        "next_cursor": cursor,
        "complete": None,
        "deletion_authority": False,
        "scope": _SCOPE,
    }


def capture_bound_scope(cfg: Any, store: Any, profile: str, public_account: str) -> str:
    from gflow_cli.config import get_settings
    from gflow_cli.selfhost.account_marker import read_verified_account

    configured = cfg.accounts.get(profile)
    registered = store.account_lookup(public_account)
    if (
        configured is None
        or registered is None
        or registered["profile"] != profile
        or registered["enabled"] != 1
        or registered["verified"] != 1
        or registered["email"].casefold() != configured["email"].casefold()
    ):
        raise HTTPException(409, "Account registration changed before resource listing")
    principal = read_verified_account(get_settings().profile_subdir(profile))
    if principal is None:
        raise HTTPException(409, "Account resources require a private recorded principal")
    return hashlib.sha256(principal.encode()).hexdigest()


def mount(
    app: FastAPI,
    *,
    pick_account: Callable[[Any, list[str]], str],
    run: Callable[[list[str], int], Awaitable[tuple[int, bytes]]],
    bind_scope: Callable[[str, str], str],
) -> None:
    @app.get("/v1/google-flow/assets/resources/{email}")
    async def list_resources(request: Request, email: str) -> dict[str, Any]:
        from gflow_cli.services.account_resources import validate_account_resource_options

        params = request.query_params
        kind = params.get("kind", "character")
        cursor = params.get("cursor")
        try:

            def integer(name: str, default: int) -> int:
                raw = params.get(name)
                if raw is not None and re.fullmatch(r"[0-9]{1,3}", raw) is None:
                    raise ValueError("Invalid bounded resource integer")
                return int(raw) if raw is not None else default

            max_projects = integer("maxProjects", 10)
            max_pages = integer("maxPages", 1)
            max_seconds = integer("maxSeconds", 180)
            validate_account_resource_options(kind, cursor, max_projects, max_pages, max_seconds)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        profile = pick_account(email, [])
        expected_scope = bind_scope(profile, email)
        code, raw = await run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "account-resources",
                profile,
                json.dumps(
                    {
                        "kind": kind,
                        "cursor": cursor,
                        "max_projects": max_projects,
                        "max_pages": max_pages,
                        "max_seconds": max_seconds,
                        "expected_account_sha256": expected_scope,
                    }
                ),
            ],
            max_seconds + 45,
        )
        if pick_account(email, []) != profile or bind_scope(profile, email) != expected_scope:
            raise HTTPException(409, "Account scope changed during resource listing")
        try:
            if code:
                raise ValueError("Unavailable account resource worker")
            result = public_result(parse_json_output(raw), kind, max_projects, max_pages)
        except (ValueError, TypeError, KeyError):
            raise HTTPException(
                502, "Native account resources unavailable; committed progress retained"
            ) from None
        return result
