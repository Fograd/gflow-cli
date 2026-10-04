"""Automatic local routing from recorded rolling job scores, never inferred tier state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from gflow_cli.selfhost.job_statistics import statistics
from gflow_cli.selfhost.store import Store


def select_account(
    store: Store,
    configured: Mapping[str, Mapping[str, str]],
    *,
    operation: str | None = None,
    model_key: str | None = None,
) -> str:
    """Choose an exact current registration by combined score, then queue load.

    Explicit account and owned-reference callers bypass this function. Statistics
    already follows accepted refresh lineage and excludes stale terminal observations.
    A generic rate-limit status does not establish any reason/model quarantine.
    """
    summaries = cast(dict[str, dict[str, Any]], statistics(store, "summary")["combined"]["summary"])
    scores = {email.casefold(): int(row["score"]) for email, row in summaries.items()}
    candidates: list[str] = []
    for row in store.accounts():
        profile: str = row["profile"]
        email: str = row["email"]
        account = configured.get(profile)
        if (
            row["enabled"] == 1
            and row["verified"] == 1
            and account is not None
            and account["email"].casefold() == email.casefold()
            and account["project"] == row["project"]
            and email.casefold() in scores
        ):
            candidates.append(profile)
    if not candidates:
        raise ValueError("No current verified accounts configured")
    from gflow_cli.selfhost.model_quarantine import filter_accounts

    candidates = filter_accounts(
        store, configured, candidates, operation=operation, model_key=model_key
    )
    with store.connection() as conn:
        queued = dict(
            conn.execute(
                "SELECT profile,COUNT(*) FROM jobs WHERE state IN ('created','running') "
                "GROUP BY profile"
            )
        )
    return min(
        candidates,
        key=lambda profile: (
            scores[configured[profile]["email"].casefold()],
            queued.get(profile, 0),
            profile,
        ),
    )
