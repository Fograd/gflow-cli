"""Optional idle project-access scheduling; never renews authentication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING, Any

import structlog

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.session_health import public_health_observation

if TYPE_CHECKING:
    from gflow_cli.selfhost.store import Store

log = structlog.get_logger(__name__)
POLL_SECONDS = 30


def maintenance_scope(account: dict[str, Any]) -> str:
    """Opaque mapping scope; changes are reset explicitly by account_set as well."""
    identity = [account[key] for key in ("profile", "email", "project", "created")]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def maintenance_status(
    account: dict[str, Any] | None,
    last_job: dict[str, Any] | None,
    busy: bool,
    interval: float,
    now: float,
) -> dict[str, Any]:
    enabled = bool(interval and account and account["enabled"] == 1 and account["verified"] == 1)
    result: dict[str, Any] = {
        "enabled": enabled,
        "intervalSeconds": interval,
        "mode": "periodic-project-access",
        "refreshAttempted": False,
        "state": "disabled",
        "nextDueAt": None,
        "lastJobId": None,
        "lastObservation": None,
    }
    anchor = float(account["created"]) if account else now
    delay = interval
    pending = False
    if last_job:
        result["lastJobId"] = last_job["id"]
        raw: dict[str, Any] = json.loads(last_job["result"]) if last_job["result"] else {}
        pending = last_job["state"] in {"created", "running"}
        if not pending and raw.get("idleSessionMaintenanceCancelled") is not True:
            observation = public_health_observation(raw.get("sessionHealth"))
            result["lastObservation"] = observation
            anchor = float(last_job["updated"])
            factor = {"OK": 1, "UNKNOWN": 2, "LOGIN_REQUIRED": 4}[observation["health"]]
            delay = max(interval, min(interval * factor, 86400))
    if enabled:
        due = anchor + delay
        result["nextDueAt"] = None if pending else due
        result["state"] = (
            "pending" if pending else "queue_busy" if busy else "due" if now >= due else "waiting"
        )
    return result


async def maintain_idle_sessions(cfg: Settings, store: Store) -> None:
    """Admission only; existing workers own all browser and ProfileLease activity."""
    while True:
        try:
            store.cancel_idle_health(cfg.idle_session_interval, cfg.accounts)
            for profile in tuple(cfg.accounts):
                if store.enqueue_idle_health(profile, cfg.idle_session_interval):
                    break
        except sqlite3.Error:
            # No row, account, path or raw database error leaves the private boundary.
            log.warning("selfhost.idle_session_store_unavailable")
        await asyncio.sleep(POLL_SECONDS)
