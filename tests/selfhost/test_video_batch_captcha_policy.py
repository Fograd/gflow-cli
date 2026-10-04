"""Configured plural policy retries only exact negative unacknowledged WAF."""

import pytest

from gflow_cli.errors import WafRejectionError
from gflow_cli.selfhost import video_captcha_policy as policy
from tests.selfhost.test_video_captcha_policy import P, ready
from tests.selfhost.test_video_captcha_policy import environment as _environment

environment = _environment


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 3, 4])
async def test_plural_waf_then_accepted_preserves_requested_count(environment, count):
    root, stats = environment
    attempts = []

    async def attempt(override):
        attempts.append(override)
        assert override.count == count
        await override.token(ready(override))
        override.used = True
        override.dispatched = True
        override.observe("submitted")
        override.outcome("rejected" if len(attempts) == 1 else "accepted")
        if len(attempts) == 1:
            raise WafRejectionError(detail="exact negative")
        return "accepted"

    result, chosen = await policy.run_with_video_captcha_policy(
        {"count": count, "captchaRetry": 2}, P, root, attempt
    )
    assert result == "accepted" and chosen == "CapSolver" and len(attempts) == 2
    assert stats.count(("CapSolver", "solveStarted")) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["partial", "accepted", "unknown"])
async def test_plural_partial_or_accepted_never_replays(environment, failure):
    root, _ = environment
    attempts = []

    async def attempt(override):
        attempts.append(override)
        await override.token(ready(override))
        override.used = True
        override.dispatched = True
        if failure == "partial":
            override.known_media_ids.append("actual-owned-handle")
        override.outcome("accepted" if failure == "accepted" else "unknown")
        raise WafRejectionError(detail="late or mixed")

    with pytest.raises(WafRejectionError):
        await policy.run_with_video_captcha_policy(
            {"count": 4, "captchaRetry": 10}, P, root, attempt
        )
    assert len(attempts) == 1
