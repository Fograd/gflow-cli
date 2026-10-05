"""Compact private registration-epoch session observations; no browser on status reads."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from gflow_cli.selfhost.idle_session import maintenance_scope
from gflow_cli.selfhost.session_health import (
    health_observation,
    profile_identity_sha256,
    public_health_observation,
)


def bind_health_scope(conn: Any, profile: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Capture scope and pin the original expected principal once, inside admission."""
    account = conn.execute(
        "SELECT * FROM accounts WHERE profile=? AND enabled=1 AND verified=1", (profile,)
    ).fetchone()
    if account is None:
        return {**payload, "_session_scope": None, "_expected_identity_sha256": None}
    mapping = maintenance_scope(dict(account))
    row = conn.execute(
        "SELECT * FROM account_session_status WHERE profile=?", (profile,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO account_session_status(profile,epoch,mapping,identity_sha256) "
            "VALUES(?,?,?,?)",
            (profile, str(uuid.uuid4()), mapping, profile_identity_sha256(profile)),
        )
    elif row["identity_sha256"] is None:
        # No principal was ever recorded. First human login can establish the anchor.
        conn.execute(
            "UPDATE account_session_status SET identity_sha256=? WHERE profile=?",
            (profile_identity_sha256(profile), profile),
        )
    row = conn.execute(
        "SELECT * FROM account_session_status WHERE profile=?", (profile,)
    ).fetchone()
    return {
        **payload,
        "_session_scope": row["epoch"],
        "_expected_identity_sha256": row["identity_sha256"],
    }


def reset_health_scope(conn: Any, profile: str) -> None:
    """Never resurrect A's results after A→B→A; retain its expected principal anchor."""
    account = conn.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone()
    if account:
        conn.execute(
            "UPDATE account_session_status SET epoch=?,mapping=?,observation=NULL,"
            "completed=NULL,last_job=NULL,last_access=NULL,last_identity=NULL WHERE profile=?",
            (str(uuid.uuid4()), maintenance_scope(dict(account)), profile),
        )


def health_scope_current(conn: Any, job: dict[str, Any]) -> bool:
    payload = json.loads(job["payload"])
    account = conn.execute(
        "SELECT * FROM accounts WHERE profile=? AND enabled=1 AND verified=1", (job["profile"],)
    ).fetchone()
    row = conn.execute(
        "SELECT * FROM account_session_status WHERE profile=?", (job["profile"],)
    ).fetchone()
    return bool(
        account
        and row
        and payload.get("_session_scope") == row["epoch"]
        and row["mapping"] == maintenance_scope(dict(account))
        and payload.get("project") == account["project"]
        and payload.get("email", account["email"]) == account["email"]
        and payload.get("_expected_identity_sha256") == row["identity_sha256"]
    )


def record_health_observation(
    conn: Any, job: dict[str, Any], result: dict[str, Any], now: float
) -> dict[str, Any]:
    """Record only first terminal, current-scope checks; preserve historical successes."""
    if not health_scope_current(conn, job):
        return {**result, "sessionHealth": health_observation(reason="registration_changed")}
    if result.get("idleSessionMaintenanceCancelled") is True:
        return result
    observation = public_health_observation(result.get("sessionHealth"))
    # A malformed projection can have a synthetic timestamp. It cannot establish OK.
    raw: Any = result.get("sessionHealth")
    try:
        stamp = datetime.fromisoformat(raw["checkedAt"].replace("Z", "+00:00"))
        valid_stamp = (
            stamp.tzinfo is not None and job["updated"] - 1 <= stamp.timestamp() <= now + 1
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        valid_stamp = False
    if not valid_stamp:
        observation = health_observation(reason="probe_error")
    checked = observation["checkedAt"]
    successful = observation["health"] == "OK"
    conn.execute(
        "UPDATE account_session_status SET observation=?,completed=?,last_job=?,"
        "last_access=CASE WHEN ? THEN ? ELSE last_access END,"
        "last_identity=CASE WHEN ? THEN ? ELSE last_identity END WHERE profile=?",
        (
            json.dumps(observation),
            now,
            job["id"],
            successful,
            checked,
            successful and observation["identityVerified"],
            checked,
            job["profile"],
        ),
    )
    return {**result, "sessionHealth": observation}


def session_status(conn: Any, profile: str, interval: float, now: float) -> dict[str, Any]:
    account = conn.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone()
    enabled = bool(account and account["enabled"] == 1 and account["verified"] == 1)
    result: dict[str, Any] = {
        "state": "unobserved" if enabled else "disabled",
        "latestObservation": None,
        "lastJobId": None,
        "lastVerifiedAccessAt": None,
        "lastVerifiedIdentityAt": None,
        "fresh": False,
        "ageSeconds": None,
        "staleAfterSeconds": max(3600.0, 2 * interval),
        "loginRequired": False,
        "profilePreserved": True,
        "renewal": {
            "state": "unproved",
            "automaticRenewalSupported": False,
            "lastAttemptAt": None,
            "lastResult": None,
        },
    }
    if not enabled:
        return result
    row = conn.execute(
        "SELECT * FROM account_session_status WHERE profile=?", (profile,)
    ).fetchone()
    if not row or row["mapping"] != maintenance_scope(dict(account)) or not row["observation"]:
        return result
    observation = public_health_observation(json.loads(row["observation"]))
    checked = datetime.fromisoformat(observation["checkedAt"].replace("Z", "+00:00")).timestamp()
    age = max(0.0, now - checked)
    fresh = age <= result["staleAfterSeconds"] and checked <= now + 1
    result.update(
        latestObservation=observation,
        lastJobId=row["last_job"],
        lastVerifiedAccessAt=row["last_access"],
        lastVerifiedIdentityAt=row["last_identity"],
        ageSeconds=round(age, 3),
        fresh=fresh,
        loginRequired=fresh and observation["health"] == "LOGIN_REQUIRED",
        state="stale"
        if not fresh
        else "login_required"
        if observation["health"] == "LOGIN_REQUIRED"
        else "verified"
        if observation["health"] == "OK" and observation["identityVerified"]
        else "access_verified"
        if observation["health"] == "OK"
        else "unknown",
    )
    return result
