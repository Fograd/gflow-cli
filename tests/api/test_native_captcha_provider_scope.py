"""Provider minting is fresh, scoped, single use, and never replays ambiguous submits."""

from types import SimpleNamespace

import pytest

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_provider,
    native_captcha_submission,
    native_captcha_token,
    take_native_captcha_token_async,
)
from gflow_cli.errors import ConfigurationError

PROJECT = "11111111-1111-4111-8111-111111111111"
PAGE = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)


@pytest.mark.asyncio
async def test_provider_context_mints_once_and_records_exact_outcome():
    calls = []
    events = []

    async def mint(page, action):
        calls.append((page, action))
        return "a" * 40

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        assert await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION") == "a" * 40
        native_captcha_submission()
        native_captcha_outcome("accepted")
        with pytest.raises(ConfigurationError):
            await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
    assert len(calls) == 1
    assert events == ["submitted", "accepted"]


@pytest.mark.asyncio
async def test_scope_mismatch_does_not_solve_and_supplied_token_has_precedence():
    calls = []

    async def mint(page, action):
        calls.append(action)
        return "a" * 40

    with native_captcha_provider(mint, project_id=PROJECT, action="VIDEO_GENERATION"):
        with pytest.raises(ConfigurationError):
            await take_native_captcha_token_async(PAGE, "AUDIO_GENERATION")
        assert calls == []
        with native_captcha_token("b" * 40, project_id=PROJECT, action="VIDEO_GENERATION"):
            assert await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION") == "b" * 40
        assert calls == []


@pytest.mark.asyncio
async def test_solve_failure_is_not_replayed_and_unknown_only_after_submission():
    events = []

    async def mint(page, action):
        raise RuntimeError("provider down")

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        with pytest.raises(RuntimeError):
            await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
        with pytest.raises(ConfigurationError):
            await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
    assert events == []


@pytest.mark.asyncio
async def test_uncertain_dispatch_records_unknown_and_concurrent_children_share_one_use():
    import asyncio

    events = []

    async def mint(page, action):
        await asyncio.sleep(0)
        return "a" * 40

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        values = await asyncio.gather(
            take_native_captcha_token_async(PAGE, "VIDEO_GENERATION"),
            take_native_captcha_token_async(PAGE, "VIDEO_GENERATION"),
            return_exceptions=True,
        )
        assert sum(isinstance(value, ConfigurationError) for value in values) == 1
        native_captcha_submission()
    assert events == ["submitted", "unknown"]


@pytest.mark.asyncio
async def test_scope_rechecked_after_provider_await_and_duplicate_outcomes():
    events = []
    page = SimpleNamespace(url=PAGE.url)

    async def moved(page, action):
        page.url = "https://example.test/project/" + PROJECT
        return "a" * 40

    with native_captcha_provider(
        moved, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        with pytest.raises(ConfigurationError):
            await take_native_captcha_token_async(page, "VIDEO_GENERATION")
        native_captcha_submission()
    assert events == []

    async def mint(page, action):
        return "a" * 40

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
        native_captcha_submission()
        native_captcha_submission()
        native_captcha_outcome("accepted")
        native_captcha_outcome("rejected")
    assert events == ["submitted", "accepted"]


@pytest.mark.asyncio
async def test_inherited_child_cannot_mint_after_owner_context_exits():
    import asyncio

    events = []
    calls = []
    gate = asyncio.Event()

    async def mint(page, action):
        calls.append(action)
        return "a" * 40

    async def child():
        await gate.wait()
        return await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        task = asyncio.create_task(child())
    gate.set()
    with pytest.raises(ConfigurationError):
        await task
    assert calls == [] and events == []


@pytest.mark.asyncio
async def test_inflight_provider_cannot_finish_after_owner_context_exits():
    import asyncio

    events = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def mint(page, action):
        started.set()
        await release.wait()
        return "a" * 40

    with native_captcha_provider(
        mint, project_id=PROJECT, action="VIDEO_GENERATION", observe=events.append
    ):
        task = asyncio.create_task(take_native_captcha_token_async(PAGE, "VIDEO_GENERATION"))
        await started.wait()
    release.set()
    with pytest.raises(ConfigurationError):
        await task
    assert events == []
