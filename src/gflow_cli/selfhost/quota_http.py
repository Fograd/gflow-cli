"""Exact local automatic-routing refusal; other HTTP error envelopes are unchanged."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from gflow_cli.selfhost.model_quarantine import NoEligibleAccountError


class NoEligibleAccountHTTPError(Exception):
    def __init__(self, observation: NoEligibleAccountError):
        super().__init__("No eligible automatic account under local quota policy")
        self.retry_after = observation.retry_after
        self.payload: dict[str, Any] = {
            "error": "no_eligible_account",
            "code": "local_quota_policy",
            "retryAfter": observation.retry_after,
            "retryAt": datetime.fromtimestamp(observation.retry_at, UTC).isoformat(),
            "skipReasons": observation.skip_reasons,
            "policy": observation.policy,
            "resetSource": "local policy; Google reset time is unobserved",
        }
