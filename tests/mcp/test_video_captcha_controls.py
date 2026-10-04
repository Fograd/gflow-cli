"""Provider fields are nonsecret; confidential video token never enters queue."""

from unittest.mock import AsyncMock

import pytest

from gflow_cli.mcp import tools

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
async def test_confidential_token_refuses_before_queue_and_rate_limit(monkeypatch):
    queue = AsyncMock()
    limiter = AsyncMock()
    monkeypatch.setattr(tools, "_run_generation_task", queue)
    monkeypatch.setattr(tools._rate_limiter, "acquire", limiter)
    result = await tools.gflow_generate_video(
        prompt="test", project=P, captcha_token="secret-token-value-" * 3
    )
    assert result["status"] == "error"
    assert "queue" in str(result).lower()
    assert "secret-token" not in str(result)
    queue.assert_not_awaited()
    limiter.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"count": 5}, {"captcha_retry": True}, {"project": None}])
async def test_provider_controls_validate_prequeue(monkeypatch, changes):
    queue = AsyncMock()
    monkeypatch.setattr(tools, "_run_generation_task", queue)
    params = {"prompt": "test", "project": P, "captcha_retry": 2, **changes}
    result = await tools.gflow_generate_video(**params)
    assert result["status"] == "error"
    assert result["error"]["title"] == "Invalid Video CAPTCHA Controls"
    queue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("wait", [True, False])
@pytest.mark.parametrize("count", [1, 2, 3, 4])
async def test_configured_providers_forward_nonsecret_controls_to_queue(monkeypatch, wait, count):
    queue = AsyncMock(return_value={"status": "queued"})
    monkeypatch.setattr(tools, "_run_generation_task", queue)
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "pro1")
    result = await tools.gflow_generate_video(
        prompt="test",
        project=P,
        captcha_order="CapSolver,2Captcha",
        captcha_retry=3,
        wait=wait,
        count=count,
    )
    assert result["status"] == "queued"
    assert queue.await_args.kwargs["wait"] is wait
    payload = queue.await_args.kwargs["payload"]
    assert payload["count"] == count
    assert payload["captchaOrder"] == "CapSolver,2Captcha" and payload["captchaRetry"] == 3
    assert not any("token" in key.lower() for key in payload)
