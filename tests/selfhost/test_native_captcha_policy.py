"""Only explicit negatively acknowledged WAF refusals may spend another attempt."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_provider,
    native_captcha_submission,
    take_native_captcha_token_async,
)
from gflow_cli.errors import (
    AuthExpiredError,
    ContentPolicyError,
    NativeVideoGenerationUnknownError,
    VoiceMutationUnknownError,
    WafRejectionError,
)
from gflow_cli.selfhost import native_captcha_policy as policy

P = "11111111-1111-4111-8111-111111111111"
PAGE = SimpleNamespace(url=f"https://flow.google.com/project/{P}")


@pytest.fixture
def scopes(monkeypatch):
    seen = {"contexts": [], "events": [], "tokens": []}

    @contextmanager
    def context(payload, project, action):
        seen["contexts"].append(dict(payload))

        async def mint(page, mint_action):
            value = "a" * 40 + str(len(seen["contexts"]))
            seen["tokens"].append(value)
            return value

        with native_captcha_provider(
            mint, project_id=project, action=action, observe=seen["events"].append
        ):
            yield

    monkeypatch.setattr(policy, "private_native_captcha", context)
    return seen


async def mint_and_dispatch():
    await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
    native_captcha_submission()


@pytest.mark.asyncio
async def test_two_refusals_then_acceptance_fresh_scopes(scopes):
    calls = []

    async def attempt():
        calls.append(1)
        await mint_and_dispatch()
        if len(calls) <= 2:
            native_captcha_outcome("rejected")
            raise WafRejectionError()
        native_captcha_outcome("accepted")
        return {"ok": True}

    result = await policy.run_with_native_captcha_policy(
        {"captchaRetry": 3}, P, "VIDEO_GENERATION", attempt
    )
    assert result == {"ok": True} and len(calls) == 3
    assert len(set(scopes["tokens"])) == 3
    assert all(p["captchaRetry"] == 1 for p in scopes["contexts"])
    assert scopes["events"] == [
        "submitted",
        "rejected",
        "submitted",
        "rejected",
        "submitted",
        "accepted",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        ContentPolicyError(),
        AuthExpiredError(),
        RuntimeError("throttle"),
        NativeVideoGenerationUnknownError(
            project_id=P,
            media_ids=("22222222-2222-4222-8222-222222222222",),
            workflow_ids=("33333333-3333-4333-8333-333333333333",),
            phase="video_poll",
        ),
        VoiceMutationUnknownError(
            project_id=P,
            phase="save",
            media_id="22222222-2222-4222-8222-222222222222",
            workflow_id="33333333-3333-4333-8333-333333333333",
        ),
    ],
)
async def test_non_waf_errors_never_retry(scopes, error):
    calls = []

    async def attempt():
        calls.append(1)
        await mint_and_dispatch()
        raise error

    with pytest.raises(type(error)):
        await policy.run_with_native_captcha_policy(
            {"captchaRetry": 10}, P, "VIDEO_GENERATION", attempt
        )
    assert len(calls) == 1 and scopes["events"] == ["submitted", "unknown"]


@pytest.mark.asyncio
@pytest.mark.parametrize("late", [False, True])
async def test_waf_without_negative_ack_or_after_acceptance_never_retries(scopes, late):
    calls = []

    async def attempt():
        calls.append(1)
        await mint_and_dispatch()
        if late:
            native_captcha_outcome("accepted")
        raise WafRejectionError()

    with pytest.raises(WafRejectionError):
        await policy.run_with_native_captcha_policy(
            {"captchaRetry": 10}, P, "VIDEO_GENERATION", attempt
        )
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [{}, {"captchaOrder": "CapSolver"}, {"captchaSecret": "private"}]
)
async def test_defaults_and_supplied_tokens_are_one_attempt(scopes, payload):
    calls = []

    async def attempt():
        calls.append(1)
        await mint_and_dispatch()
        native_captcha_outcome("rejected")
        raise WafRejectionError()

    with pytest.raises(WafRejectionError):
        await policy.run_with_native_captcha_policy(payload, P, "VIDEO_GENERATION", attempt)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_bound_ten_and_cancel_unwinds_scope(scopes):
    calls = []

    async def refused():
        calls.append(1)
        await mint_and_dispatch()
        native_captcha_outcome("rejected")
        raise WafRejectionError()

    with pytest.raises(WafRejectionError):
        await policy.run_with_native_captcha_policy(
            {"captchaRetry": 10}, P, "VIDEO_GENERATION", refused
        )
    assert len(calls) == 10

    async def cancelled():
        await mint_and_dispatch()
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await policy.run_with_native_captcha_policy(
            {"captchaRetry": 10}, P, "VIDEO_GENERATION", cancelled
        )
    assert len(scopes["contexts"]) == 11 and scopes["events"][-2:] == ["submitted", "unknown"]
    assert await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 11, True, "2", None])
async def test_invalid_explicit_budget_before_operation(scopes, value):
    calls = []

    async def attempt():
        calls.append(1)

    with pytest.raises(ValueError):
        await policy.run_with_native_captcha_policy(
            {"captchaRetry": value}, P, "VIDEO_GENERATION", attempt
        )
    assert calls == [] and scopes["contexts"] == []
