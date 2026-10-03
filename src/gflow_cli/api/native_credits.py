"""Source-derived native GetCredits; unmapped components remain unknown."""

from __future__ import annotations

from typing import Any, cast

from gflow_cli.api.dto import CreditsInfo
from gflow_cli.api.native_extension import _NATIVE_FETCH  # pyright: ignore[reportPrivateUsage]
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.errors import WireFormatError

PAYGATE = {
    0: "PAYGATE_TIER_UNSPECIFIED",
    5: "PAYGATE_TIER_ZERO",
    1: "PAYGATE_TIER_ONE",
    7: "PAYGATE_TIER_GEMNOVA",
    2: "PAYGATE_TIER_TWO",
    3: "PAYGATE_TIER_NOT_PAID",
    4: "PAYGATE_TIER_UNSUBSCRIBED_WITH_CREDITS",
    6: "PAYGATE_TIER_EXEMPT",
    8: "PAYGATE_TIER_TIER1P5",
}
SERVICE = {
    0: "SERVICE_TIER_UNSPECIFIED",
    1: "SERVICE_TIER_ENTRY",
    2: "SERVICE_TIER_INTERMEDIATE",
    3: "SERVICE_TIER_ADVANCED",
}


def parse_native_credits(payload: Any) -> CreditsInfo:
    if not isinstance(payload, list) or not payload:
        raise ValueError("Native credit balance is unavailable")
    row = cast(list[Any], payload)
    if type(row[0]) is not int or row[0] < 0:
        raise ValueError("Native credit balance must be a nonnegative integer")
    paygate = row[1] if len(row) > 1 else None
    service = row[3] if len(row) > 3 else None
    return CreditsInfo(
        credits=row[0],
        user_paygate_tier=PAYGATE.get(paygate) if type(paygate) is int else None,
        service_tier=SERVICE.get(service) if type(service) is int else None,
    )


async def read_native_credits(page: Any) -> CreditsInfo:
    result = await page.evaluate(_NATIVE_FETCH, {"rpc": "nzlxg", "args": [], "source": "/"})
    if result["status"] != 200 or rpc_errors(result["text"]):
        raise WireFormatError(detail="Native credits were not acknowledged", route="credits.native")
    replies = [data for name, data in parse_frames(result["text"]) if name == "nzlxg"]
    if len(replies) != 1:
        raise WireFormatError(
            detail="Native credits response was ambiguous", route="credits.native"
        )
    try:
        return parse_native_credits(replies[0])
    except ValueError as exc:
        raise WireFormatError(detail=str(exc), route="credits.native") from None
