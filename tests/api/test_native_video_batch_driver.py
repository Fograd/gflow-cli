import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.native_extension import assigned_id
from gflow_cli.api.transports.native_video_batch_driver import submit_batch
from gflow_cli.errors import NativeUIVideoBatchUnknownError, WireFormatError
from tests.api.test_native_video_batch_codec import P, S, W, body, payload, row


def text(rows):
    return json.dumps([["wrb.fr", "YhhmEf", json.dumps(payload(rows)), None, None]])


class Page:
    def __init__(self, rows, *, duplicate=False, foreign=False, wrong_count=False):
        self.rows = rows
        self.listeners = {}
        self.guard = None
        self.duplicate = duplicate
        self.foreign = foreign
        self.wrong_count = wrong_count
        self.request = SimpleNamespace(
            url="https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute",
            method="POST",
            post_data=body(seeds=S[:1] if wrong_count else S),
        )
        self.route = SimpleNamespace(fallback=AsyncMock(), abort=AsyncMock(), continue_=AsyncMock())
        self.button = SimpleNamespace(
            count=AsyncMock(return_value=1), is_enabled=AsyncMock(return_value=True)
        )

    def on(self, event, callback):
        self.listeners[event] = callback

    def remove_listener(self, event, callback):
        self.listeners.pop(event, None)

    async def route(self, pattern, guard):
        self.guard = guard

    async def unroute(self, pattern, guard):
        self.guard = None

    def locator(self, selector):
        return SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=self.button))


@pytest.mark.asyncio
async def test_exact_queryless_two_output_ack_checkpoints_all_before_return():
    media = tuple(assigned_id(seed) for seed in S)
    page = Page([row(media[1], W[1]), row(media[0], W[0])])
    known = []
    dispatch = []

    # Shadow fixture route object with name distinct from method.
    route = page.route
    page.route = Page.route.__get__(page)

    async def click(*a, **kw):
        await page.guard(route, page.request)
        await page.listeners["response"](
            SimpleNamespace(request=page.request, text=AsyncMock(return_value=text(page.rows)))
        )

    async def checkpoint(pairs):
        known.append(pairs)

    result = await submit_batch(
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
        on_dispatch=lambda: dispatch.append(1),
        on_known=checkpoint,
    )
    assert result == tuple(zip(media, W, strict=True))
    assert dispatch == [1] and set(known[0]) == set(result)
    assert route.continue_.await_count == 1 and not page.listeners and page.guard is None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["partial", "duplicate_frame", "masked"])
async def test_unknown_never_replays_and_retains_actual_pairs(case):
    media = tuple(assigned_id(seed) for seed in S)
    rows = [row(media[0], W[0])]
    page = Page(rows)
    route = page.route
    page.route = Page.route.__get__(page)

    async def click(*a, **kw):
        await page.guard(route, page.request)
        message = text(rows)
        if case == "duplicate_frame":
            message = json.dumps(
                [
                    ["wrb.fr", "YhhmEf", json.dumps(payload(rows))],
                    ["wrb.fr", "YhhmEf", json.dumps(payload(rows))],
                ]
            )
        if case == "masked":
            message = json.dumps([["wrb.fr", "YhhmEf", None]])
        await page.listeners["response"](
            SimpleNamespace(request=page.request, text=AsyncMock(return_value=message))
        )

    with pytest.raises(NativeUIVideoBatchUnknownError) as exc:
        await submit_batch(
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
    assert exc.value.media_ids == (() if case == "masked" else (media[0],))
    assert route.continue_.await_count == 1 and not page.listeners


@pytest.mark.asyncio
async def test_wrong_count_aborts_before_google():
    page = Page([], wrong_count=True)
    route = page.route
    page.route = Page.route.__get__(page)

    async def click(*a, **kw):
        await page.guard(route, page.request)

    with pytest.raises(WireFormatError):
        await submit_batch(
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
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_unroute_failure_preserves_actual_handles_and_removes_listener(partial):
    media = tuple(assigned_id(seed) for seed in S)
    rows = [row(media[0], W[0])]
    if not partial:
        rows.append(row(media[1], W[1]))
    page = Page(rows)
    route = page.route
    page.route = Page.route.__get__(page)
    page.unroute = AsyncMock(side_effect=RuntimeError("private cleanup failure"))

    async def click(*args, **kwargs):
        await page.guard(route, page.request)
        await page.listeners["response"](
            SimpleNamespace(
                request=page.request,
                text=AsyncMock(return_value=text(rows)),
            )
        )

    with pytest.raises(NativeUIVideoBatchUnknownError) as caught:
        await submit_batch(
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
    assert caught.value.media_ids == (media[:1] if partial else media)
    assert "private cleanup failure" not in str(caught.value)
    assert not page.listeners
    route.continue_.assert_awaited_once()
