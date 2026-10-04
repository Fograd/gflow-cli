"""Controlled batch dispatch owns one token and all correlated output handles."""

import asyncio
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.native_extension import assigned_id
from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides
from gflow_cli.api.transports.native_video_batch_driver import submit_batch
from gflow_cli.errors import NativeUIVideoBatchUnknownError
from gflow_cli.selfhost.video_captcha_policy import run_with_video_captcha_policy
from tests.api.test_native_video_batch_codec import P, S, W, row
from tests.api.test_native_video_batch_driver import Page, text
from tests.api.test_video_batch_captcha_vectors import cap_body
from tests.selfhost.test_video_captcha_policy import environment as _environment
from tests.selfhost.test_video_captcha_policy import ready

environment = _environment


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_real_driver_policy_common_token_exact_handles_empty_callback_context(
    environment, partial
):
    root, stats = environment
    media = tuple(assigned_id(seed) for seed in S)
    rows = [row(media[0], W[0])]
    if not partial:
        rows.append(row(media[1], W[1]))
    page = Page(rows)
    page.url = "https://flow.google.com/project/" + P
    page.request.post_data = cap_body("YhhmEf")
    route = page.route
    page.route = Page.route.__get__(page)
    attempts = []

    async def attempt(override):
        attempts.append(override)
        ready(override)

        async def click(*args, **kwargs):
            # Playwright callback tasks may carry no caller ContextVars.
            task = Context().run(asyncio.create_task, page.guard(route, page.request))
            await task
            task = Context().run(
                asyncio.create_task,
                page.listeners["response"](
                    SimpleNamespace(request=page.request, text=AsyncMock(return_value=text(rows)))
                ),
            )
            await task

        return await submit_batch(
            page,
            SimpleNamespace(_click=click),
            project=P,
            count=2,
            rpcid="YhhmEf",
            timeout=1,
            start=None,
            end=None,
            references=(),
            characters=(),
            on_dispatch=None,
            on_known=None,
        )

    if partial:
        with pytest.raises(NativeUIVideoBatchUnknownError) as error:
            await run_with_video_captcha_policy({"count": 2, "captchaRetry": 10}, P, root, attempt)
        assert error.value.media_ids == media[:1]
        assert ("CapSolver", "unknown") in stats
    else:
        result, provider = await run_with_video_captcha_policy(
            {"count": 2, "captchaRetry": 10}, P, root, attempt
        )
        assert result == tuple(zip(media, W, strict=True)) and provider == "CapSolver"
        assert ("CapSolver", "accepted") in stats
    assert len(attempts) == 1 and ("CapSolver", "submitted") in stats
    assert route.continue_.await_count == 1
    assert "post_data" in route.continue_.await_args.kwargs
    assert active_video_overrides.get() is None and not page.listeners
