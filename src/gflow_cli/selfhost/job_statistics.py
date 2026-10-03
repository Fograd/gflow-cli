"""Read-only public account-load statistics from one durable queue snapshot."""

from __future__ import annotations

import math
import sqlite3
import time
from typing import Any

from gflow_cli.selfhost.http_jobs import EXIT_HTTP_STATUS
from gflow_cli.selfhost.store import Store

_OPTIONS = {"summary", "executing", "history"}
_FAMILIES = {
    "images": "images",
    "images/upscale": "images",
    "videos": "videos",
    "videos/reference": "videos",
    "videos/edit": "videos",
    "videos/extend": "videos",
    "videos/promote": "videos",
}


def statistics(store: Store, option: str) -> dict[str, Any]:
    """Report recorded jobs only; timings include waiting after acceptance."""
    if option not in _OPTIONS:
        raise ValueError("Invalid options parameter. Use: summary, executing, or history")
    now = time.time()
    kinds = ",".join("?" for _ in _FAMILIES)
    family_case = (
        "CASE j.kind "
        + " ".join(
            "WHEN '" + kind + "' THEN '" + family + "'" for kind, family in _FAMILIES.items()
        )
        + " END"
    )
    status_case = (
        "CASE code "
        + " ".join(
            "WHEN " + str(code) + " THEN " + str(status)
            for code, status in EXIT_HTTP_STATUS.items()
        )
        + " ELSE 502 END"
    )
    base = f"""
      WITH selected AS (
        SELECT j.id,j.profile,a.email,{family_case} family,j.state,j.created,j.updated,
          CASE WHEN json_valid(j.result) THEN
            CASE WHEN json_type(j.result,'$.error.exit_code')='integer'
                 THEN json_extract(j.result,'$.error.exit_code') END END code
        FROM jobs j JOIN accounts a ON a.profile=j.profile
        WHERE a.enabled=1 AND a.verified=1 AND j.kind IN ({kinds})
          AND (j.state='running' OR
            (j.state IN ('completed','failed','interrupted') AND j.updated>=? AND j.updated<=?))
      ), observed AS (
        SELECT *,CASE WHEN state='completed' THEN 200 WHEN state='interrupted' THEN 502
          ELSE {status_case} END http_status,
          CASE WHEN updated>=created THEN (updated-created)*1000 END duration
        FROM selected
      )
    """
    params = (*_FAMILIES, now - 900, now)
    with store.connection() as conn:
        conn.execute("BEGIN")
        accounts = conn.execute(
            "SELECT profile,email FROM accounts WHERE enabled=1 AND verified=1 ORDER BY email"
        ).fetchall()
        groups = conn.execute(
            base
            + """
          SELECT profile,family,
            SUM(state='running') executing,
            SUM(state='completed') completed,
            SUM(state IN ('failed','interrupted') AND http_status!=429) failed,
            SUM(state IN ('failed','interrupted') AND http_status=429) rate_limited,
            SUM(CASE WHEN state!='running' THEN duration ELSE 0 END) total_duration,
            COUNT(CASE WHEN state!='running' THEN duration END) duration_count
          FROM observed GROUP BY profile,family
        """,
            params,
        ).fetchall()
        running: list[sqlite3.Row] = (
            conn.execute(
                base
                + """
          SELECT id,email,family,created FROM observed WHERE state='running' ORDER BY created,id
        """,
                params,
            ).fetchall()
            if option != "summary"
            else []
        )
        history: list[sqlite3.Row] = (
            conn.execute(
                base
                + """
          SELECT id,email,family,updated,http_status,duration FROM (
            SELECT *,ROW_NUMBER() OVER (PARTITION BY family ORDER BY updated DESC,id DESC) rank
            FROM observed WHERE state!='running'
          ) WHERE rank<=10 ORDER BY updated DESC,id DESC
        """,
                params,
            ).fetchall()
            if option == "history"
            else []
        )
    result: dict[str, Any] = {
        "emails": [row["email"] for row in accounts],
        "timingPolicy": "accepted-to-observation-or-terminal",
        "rateLimitScope": "recorded-terminal-jobs",
    }
    totals: dict[tuple[str, str], tuple[float, int]] = {}
    for family in ("images", "videos", "combined"):
        result[family] = {
            "summary": {
                row["email"]: {
                    "executing": 0,
                    "completed": 0,
                    "failed": 0,
                    "rateLimited": 0,
                    "avgResponseTime": None,
                    "score": 0,
                }
                for row in accounts
            }
        }
        if family != "combined" and option != "summary":
            result[family]["executing"] = {}
        if family != "combined" and option == "history":
            result[family]["history"] = {}
    profiles = {row["profile"]: row["email"] for row in accounts}
    for row in groups:
        email = profiles[row["profile"]]
        for family in (row["family"], "combined"):
            summary = result[family]["summary"][email]
            for target, source in (
                ("executing", "executing"),
                ("completed", "completed"),
                ("failed", "failed"),
                ("rateLimited", "rate_limited"),
            ):
                summary[target] += row[source]
            total, count = totals.get((family, email), (0.0, 0))
            totals[(family, email)] = (
                total + (row["total_duration"] or 0),
                count + row["duration_count"],
            )
    for family in ("images", "videos", "combined"):
        for email, summary in result[family]["summary"].items():
            summary["score"] = (
                summary["executing"]
                + summary["completed"]
                + 10 * summary["failed"]
                + 20 * summary["rateLimited"]
            )
            total, count = totals.get((family, email), (0.0, 0))
            summary["avgResponseTime"] = round(total / count, 2) if count else None
    for row in running:
        elapsed = max(0, math.floor(now - row["created"]))
        result[row["family"]]["executing"][row["id"]] = {
            "email": row["email"],
            "timestamp": int(row["created"] * 1000),
            "elapsed": f"{elapsed // 60}:{elapsed % 60:02d}",
        }
    for row in history:
        result[row["family"]]["history"][row["id"]] = {
            "email": row["email"],
            "timestamp": int(row["updated"] * 1000),
            "httpStatus": row["http_status"],
            "responseTime": round(row["duration"], 2) if row["duration"] is not None else None,
        }
    return result
