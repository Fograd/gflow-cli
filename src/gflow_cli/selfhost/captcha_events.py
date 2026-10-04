"""Timestamped local phase observations, distinct from vendor-wide request statistics."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def query_events(
    root: Path, *, date: object = None, limit: object = None, provider: object = None
) -> dict[str, Any]:
    if date is not None:
        if not isinstance(date, str):
            raise ValueError("date requires YYYY-MM-DD")
        try:
            parsed = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError("date requires a valid YYYY-MM-DD") from None
        if parsed != date:
            raise ValueError("date requires YYYY-MM-DD")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 50000):
        raise ValueError("limit requires an integer from 1 to 50000")
    if provider not in (None, "CapSolver", "2Captcha", "UserProvided"):
        raise ValueError("provider requires CapSolver, 2Captcha or UserProvided")
    from gflow_cli.selfhost.captcha import CaptchaStats

    stats = CaptchaStats(root)
    where: list[str] = []
    values: list[Any] = []
    applied_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    if limit is None:
        where.append("substr(timestamp,1,10)=?")
        values.append(applied_date)
    if provider is not None:
        where.append("provider=?")
        values.append("supplied" if provider == "UserProvided" else provider)
    clause = " WHERE " + " AND ".join(where) if where else ""
    with sqlite3.connect(stats.path) as conn:
        rows = conn.execute(
            "SELECT timestamp,provider,phase FROM events" + clause + " ORDER BY id DESC LIMIT ?",
            (*values, limit or 50000),
        ).fetchall()
    data = [
        {
            "timestamp": ts,
            "provider": "UserProvided" if name == "supplied" else name,
            "phase": phase,
        }
        for ts, name, phase in reversed(rows)
    ]
    outcomes = {
        phase: sum(row["phase"] == phase for row in data)
        for phase in ("accepted", "rejected", "unknown")
    }
    denominator = outcomes["accepted"] + outcomes["rejected"]
    result: dict[str, Any] = {
        "scope": "this-self-hosted-instance-event-observations",
        "total": len(data),
        "data": data,
        "summary": {
            **outcomes,
            "acceptanceRate": round(outcomes["accepted"] * 100 / denominator, 2)
            if denominator
            else None,
            "confirmedOutcomeCount": denominator,
            "from": data[0]["timestamp"] if data else None,
            "to": data[-1]["timestamp"] if data else None,
        },
        "historicalAggregateEventsUnavailable": True,
    }
    result["limit" if limit is not None else "date"] = limit if limit is not None else applied_date
    if provider is not None:
        result["provider"] = provider
    return result
