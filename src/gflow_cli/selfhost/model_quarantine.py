"""Local useapi-compatible cooldown policy from positively typed native observations."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from gflow_cli.errors import NATIVE_QUOTA_CODES

POLICY = "useapi-compatible-local-policy-v1"
PROOF = "single-typed-native-rpc-v1"
_OPERATIONS = {
    "images",
    "images/upscale",
    "videos",
    "videos/reference",
    "videos/edit",
    "videos/extend",
    "videos/promote",
}
_GLOBAL = {"PUBLIC_ERROR_USER_REQUESTS_THROTTLED", "PUBLIC_ERROR_USER_QUOTA_REACHED"}


def quota_metadata(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Validate the exact safe producer projection, never arbitrary reason strings."""
    reason = raw.get("nativeReason")
    if (
        not isinstance(reason, str)
        or reason not in NATIVE_QUOTA_CODES
        or type(raw.get("nativeGrpcCode")) is not int
        or raw["nativeGrpcCode"] != NATIVE_QUOTA_CODES[reason]
        or raw.get("nativeProof") != PROOF
        or raw.get("outcome_unknown") is True
        or raw.get("outcomeUnknown") is True
    ):
        return None
    result: dict[str, Any] = {
        "nativeReason": reason,
        "nativeGrpcCode": raw["nativeGrpcCode"],
        "nativeProof": PROOF,
    }
    model = raw.get("nativeModelKey")
    operation = raw.get("nativeOperation")
    if model is not None:
        if (
            not isinstance(model, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{1,199}", model) is None
        ):
            return None
        result["nativeModelKey"] = model
    if operation is not None:
        if not isinstance(operation, str) or operation not in _OPERATIONS:
            return None
        result["nativeOperation"] = operation
    return result


def job_quota_metadata(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Accept only the canonical terminal refusal emitted by the private worker."""
    metadata = quota_metadata(raw)
    if metadata is None or type(raw.get("exit_code")) is not int or raw["exit_code"] != 4:
        return None
    expected = (
        "google_flow_model_access_denied"
        if metadata["nativeReason"] == "PUBLIC_ERROR_MODEL_ACCESS_DENIED"
        else "google_flow_native_quota"
    )
    return metadata if raw.get("code") == expected else None


def record_quarantine(conn: Any, job: str, kind: str, profile: str, error: Any, now: float) -> None:
    """Record local policy atomically with a terminal job, retaining immutable job scopes."""
    if not isinstance(error, dict) or kind not in _OPERATIONS:
        return
    metadata = job_quota_metadata(cast(dict[str, Any], error))
    if metadata is None:
        return
    reason = metadata["nativeReason"]
    if reason in _GLOBAL:
        operation, model, until = "*", "*", now + 1800
    elif reason in {
        "PUBLIC_ERROR_MODEL_ACCESS_DENIED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED_UPGRADEABLE",
    }:
        operation = metadata.get("nativeOperation")
        model = metadata.get("nativeModelKey")
        if operation != kind or model is None:
            return
        until = (
            now + 3600
            if reason == "PUBLIC_ERROR_MODEL_ACCESS_DENIED"
            else (
                datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1)
            ).timestamp()
        )
    else:
        # Positive per-request traffic rejection is not an account/model cooldown.
        return
    account = conn.execute(
        "SELECT a.email,a.created FROM accounts a "
        "LEFT JOIN account_profile_lineage l ON l.profile=? "
        "WHERE a.profile=COALESCE(l.current_profile,?) AND a.enabled=1 AND a.verified=1 "
        "AND (l.account IS NULL OR l.account=a.email)",
        (profile, profile),
    ).fetchone()
    if account is None:
        return
    scope = (account["email"], account["created"], operation, model, reason)
    previous = conn.execute(
        "SELECT * FROM model_quarantines WHERE account=? AND registration=? "
        "AND operation=? AND model=? AND reason=?",
        scope,
    ).fetchone()
    if previous is not None and previous["last_job"] == job:
        return
    conn.execute(
        "INSERT INTO model_quarantines VALUES(?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(account,registration,operation,model,reason) DO UPDATE SET "
        "until=MAX(model_quarantines.until,excluded.until),last_job=excluded.last_job",
        (*scope, now, until, job, POLICY),
    )


class NoEligibleAccountError(ValueError):
    """All automatic alternatives are covered by active local cooldowns."""

    def __init__(self, skips: list[dict[str, Any]], retry_at: float, now: float) -> None:
        super().__init__("No eligible account under active local quota policy")
        self.retry_at = retry_at
        self.retry_after = max(1, math.ceil(retry_at - now))
        self.skip_reasons = [
            {k: v for k, v in row.items() if k in {"email", "reason", "model"}} for row in skips
        ]
        self.policy = POLICY


NoEligibleAccount = NoEligibleAccountError


def filter_accounts(
    store: Any,
    configured: Mapping[str, Mapping[str, str]],
    candidates: list[str],
    *,
    operation: str | None,
    model_key: str | None,
) -> list[str]:
    """Metadata reads, pinned callers and a single valid account never get filtered."""
    if operation is None or operation not in _OPERATIONS or len(candidates) <= 1:
        return candidates
    now = time.time()
    skips: list[dict[str, Any]] = []
    remaining: list[str] = []
    retry_by_profile: list[float] = []
    with store.connection() as conn:
        for profile in candidates:
            rows = conn.execute(
                "SELECT q.*,a.email FROM model_quarantines q JOIN accounts a "
                "ON q.account=a.email AND q.registration=a.created "
                "WHERE a.profile=? AND q.until>? AND q.policy=? AND "
                "(q.operation='*' OR (q.operation=? AND q.model=?)) "
                "ORDER BY q.until DESC,q.reason",
                (profile, now, POLICY, operation, model_key),
            ).fetchall()
            if not rows:
                remaining.append(profile)
            else:
                retry_by_profile.append(rows[0]["until"])
                skips.extend(
                    {
                        "email": configured[profile]["email"],
                        "reason": row["reason"],
                        "model": row["model"],
                    }
                    for row in rows
                )
    if not remaining:
        raise NoEligibleAccount(skips, min(retry_by_profile), now)
    return remaining
