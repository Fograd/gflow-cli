"""Explicit count-one video provider policy, offline and no external solves."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import WafRejectionError, WireFormatError
from gflow_cli.selfhost import video_captcha_policy as policy

P = "11111111-1111-4111-8111-111111111111"
TOKEN = "valid-private-test-token-" * 3
KEY = "trusted_sitekey_123456789012345"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    stats = []
    monkeypatch.setattr(
        policy, "ProviderKeys", lambda root: SimpleNamespace(get=lambda name: "secret")
    )
    monkeypatch.setattr(
        policy,
        "CaptchaStats",
        lambda root: SimpleNamespace(record=lambda *args: stats.append(args)),
    )
    monkeypatch.setattr(policy, "discover_site_key", AsyncMock(return_value=KEY))
    monkeypatch.setattr(
        policy,
        "Solver",
        lambda: SimpleNamespace(solve=AsyncMock(return_value=SimpleNamespace(token=TOKEN))),
    )
    return tmp_path, stats


def payload(**kwargs):
    return {"count": 1, "captchaRetry": 1, **kwargs}


def ready(override):
    import time

    override.metadata = {"sitekey": KEY, "action": "VIDEO_GENERATION"}
    override.metadata_url = "https://flow.google.com/project/" + P
    override.metadata_at = time.monotonic()
    return SimpleNamespace(url=override.metadata_url)


@pytest.mark.asyncio
async def test_two_positive_waf_refusals_then_accepted(environment):
    root, stats = environment
    attempts = []

    async def attempt(override):
        attempts.append(override)
        await override.token(ready(override))
        override.used = True
        override.dispatched = True
        override.observe("submitted")
        override.outcome("rejected" if len(attempts) < 3 else "accepted")
        if len(attempts) < 3:
            raise WafRejectionError(detail="explicit native rejection")
        return "result"

    value, chosen = await policy.run_with_video_captcha_policy(
        payload(captchaRetry=3), P, root, attempt
    )
    assert (value, chosen) == ("result", "CapSolver")
    assert len(attempts) == 3 and all(item.closed for item in attempts)
    assert stats.count(("CapSolver", "solveStarted")) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown", "accepted", "unsubmitted", "content"])
async def test_uncertain_or_accepted_attempt_never_retries(environment, failure):
    root, stats = environment
    calls = []

    async def attempt(override):
        calls.append(override)
        await override.token(ready(override))
        if failure != "unsubmitted":
            override.used = True
            override.dispatched = True
            override.outcome("accepted" if failure == "accepted" else "unknown")
        if failure == "content":
            raise WireFormatError(detail="content or malformed")
        raise WafRejectionError(detail="late or unrelated rejection")

    with pytest.raises((WafRejectionError, WireFormatError)):
        await policy.run_with_video_captcha_policy(payload(captchaRetry=10), P, root, attempt)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"count": 5},
        {"count": True},
        {"captchaRetry": 0},
        {"captchaRetry": 11},
        {"captchaRetry": True},
        {"captchaOrder": "Unknown"},
        {"captchaOrder": "CapSolver,CapSolver"},
    ],
)
async def test_controls_fail_before_attempt(environment, changes):
    root, _ = environment
    attempt = AsyncMock()
    with pytest.raises(ValueError):
        await policy.run_with_video_captcha_policy(payload(**changes), P, root, attempt)
    attempt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {"sitekey": KEY, "action": "IMAGE_GENERATION"},
        {"sitekey": "different-key", "action": "VIDEO_GENERATION"},
    ],
)
async def test_missing_wrong_metadata_refuses_before_solve(environment, metadata, monkeypatch):
    root, stats = environment
    solve = AsyncMock()
    monkeypatch.setattr(policy, "Solver", lambda: SimpleNamespace(solve=solve))

    async def attempt(override):
        page = ready(override)
        override.metadata = metadata
        return await override.token(page)

    with pytest.raises(Exception, match="metadata"):
        await policy.run_with_video_captcha_policy(payload(), P, root, attempt)
    solve.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplied_precedence_single_attempt_without_solver(
    environment, tmp_path, monkeypatch
):
    root, stats = environment
    directory = root / "captcha-input"
    directory.mkdir()
    file = directory / ("a" * 64 + ".token")
    file.write_text(TOKEN)
    file.chmod(0o600)
    solve = AsyncMock()
    monkeypatch.setattr(policy, "Solver", lambda: SimpleNamespace(solve=solve))
    calls = []

    async def attempt(override):
        calls.append(override)
        assert (
            await override.token(SimpleNamespace(url="https://flow.google.com/project/" + P))
            == TOKEN
        )
        override.dispatched = True
        override.outcome("rejected")
        raise WafRejectionError(detail="rejected")

    with pytest.raises(WafRejectionError):
        await policy.run_with_video_captcha_policy(
            {"count": 1, "captchaSecret": str(file)}, P, root, attempt
        )
    assert len(calls) == 1 and not file.exists()
    solve.assert_not_awaited()


@pytest.mark.asyncio
async def test_maximum_ten_positive_refusals_exhaust_without_eleventh(environment):
    root, _ = environment
    calls = []

    async def attempt(override):
        calls.append(override)
        await override.token(ready(override))
        override.dispatched = True
        override.outcome("rejected")
        raise WafRejectionError(detail="explicit")

    with pytest.raises(WafRejectionError):
        await policy.run_with_video_captcha_policy(payload(captchaRetry=10), P, root, attempt)
    assert len(calls) == 10


@pytest.mark.asyncio
async def test_invalid_provider_token_falls_back_before_submission(environment, monkeypatch):
    root, stats = environment
    solve = AsyncMock(
        side_effect=[SimpleNamespace(token="bad token" * 10), SimpleNamespace(token=TOKEN)]
    )
    monkeypatch.setattr(policy, "Solver", lambda: SimpleNamespace(solve=solve))

    async def attempt(override):
        assert await override.token(ready(override)) == TOKEN
        override.dispatched = True
        override.observe("submitted")
        override.outcome("accepted")
        return "done"

    assert await policy.run_with_video_captcha_policy(payload(), P, root, attempt) == (
        "done",
        "2Captcha",
    )
    assert ("CapSolver", "solveFailed") in stats
    assert ("CapSolver", "submitted") not in stats
    assert ("2Captcha", "accepted") in stats


@pytest.mark.asyncio
async def test_child_token_consumer_after_owner_exit_is_closed(environment):
    import asyncio

    root, stats = environment
    gate = asyncio.Event()

    async def attempt(override):
        page = ready(override)

        async def child():
            await gate.wait()
            return await override.token(page)

        return asyncio.create_task(child())

    child, _ = await policy.run_with_video_captcha_policy(payload(), P, root, attempt)
    gate.set()
    with pytest.raises(Exception, match="closed"):
        await child
    assert not stats


@pytest.mark.asyncio
async def test_inflight_solve_cannot_complete_after_scope_closure(environment, monkeypatch):
    import asyncio

    root, stats = environment
    entered, release = asyncio.Event(), asyncio.Event()

    async def solve(*args):
        entered.set()
        await release.wait()
        return SimpleNamespace(token=TOKEN)

    monkeypatch.setattr(policy, "Solver", lambda: SimpleNamespace(solve=solve))

    async def attempt(override):
        child = asyncio.create_task(override.token(ready(override)))
        await entered.wait()
        return child

    child, _ = await policy.run_with_video_captcha_policy(payload(), P, root, attempt)
    release.set()
    with pytest.raises(Exception, match="closed|changed"):
        await child
    assert ("CapSolver", "solved") not in stats


@pytest.mark.asyncio
async def test_cancellation_records_unknown_and_never_retries(environment):
    import asyncio

    root, stats = environment
    calls = []

    async def attempt(override):
        calls.append(override)
        await override.token(ready(override))
        override.dispatched = True
        override.observe("submitted")
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await policy.run_with_video_captcha_policy(payload(captchaRetry=10), P, root, attempt)
    assert len(calls) == 1 and calls[0].closed
    assert stats.count(("CapSolver", "unknown")) == 1


@pytest.mark.asyncio
async def test_accepted_known_handle_even_explicit_refusal_never_retries(environment):
    root, _ = environment
    calls = []

    async def attempt(override):
        calls.append(override)
        await override.token(ready(override))
        override.dispatched = True
        override.known_media_ids.append(P)
        override.outcome("rejected")
        raise WafRejectionError(detail="mixed")

    with pytest.raises(WafRejectionError):
        await policy.run_with_video_captcha_policy(payload(captchaRetry=10), P, root, attempt)
    assert len(calls) == 1
