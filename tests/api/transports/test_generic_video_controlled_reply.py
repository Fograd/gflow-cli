"""Exact controlled video replies; no browser or Google calls."""

import asyncio
import json
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import migrated_composer as composer
from gflow_cli.api.transports.migrated_video_overrides import VideoOverrides, active_video_overrides
from gflow_cli.errors import WafRejectionError, WireFormatError
from tests.api.test_migrated_video_overrides import TOKEN, body
from tests.api.transports.test_migrated_composer import (
    MEDIA,
    VIDEO_URL,
    WF,
    FakePage,
    _frame,
    _record,
)

P = "22222222-2222-4222-8222-222222222222"
URL = "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "queryless",
        "waf",
        "mixed",
        "masked",
        "duplicate",
        "late",
        "foreign-refusal",
        "foreign-positive-own-positive",
        "foreign-positive-own-masked",
        "foreign-waf-own-positive",
    ],
)
async def test_exact_reply_and_known_handle_cleanup(monkeypatch, mode):
    page = FakePage(url="https://flow.google.com/project/" + P)
    page.dom.prompt = "test"
    routes = []
    override = VideoOverrides(project=P, count=1, token=AsyncMock(return_value=TOKEN))
    request = SimpleNamespace(url=URL, method="POST", post_data=body(project=P))

    async def install(pattern, handler):
        from playwright._impl._helper import url_matches

        assert url_matches(None, URL, pattern)
        routes.append(handler)

    async def unroute(pattern, handler):
        routes.remove(handler)

    page.route = install
    page.unroute = unroute
    good = ["wrb.fr", "YhhmEf", json.dumps([None, 1, [[MEDIA]], [[_record(6)]]])]
    bad = [
        "wrb.fr",
        "YhhmEf",
        None,
        None,
        None,
        [
            7,
            None,
            [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]],
        ],
    ]
    rows = {
        "waf": [bad],
        "mixed": [bad, good],
        "masked": [bad, ["wrb.fr", "YhhmEf", "[5]"]],
        "duplicate": [good, good],
    }.get(mode, [good])

    if mode.startswith("foreign-") and mode != "foreign-refusal":
        foreign_record = _record(6)
        foreign_record[2] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        foreign = ["wrb.fr", "eb1hJf", json.dumps([None, 1, [], [[foreign_record]]])]
        if mode == "foreign-waf-own-positive":
            foreign = list(bad)
            foreign[1] = "eb1hJf"
        own = ["wrb.fr", "YhhmEf", "[5]"] if mode.endswith("masked") else good
        rows = [foreign, own]

    async def respond(rows, actual_request=request):
        response = SimpleNamespace(
            url=URL,
            request=actual_request,
            text=AsyncMock(return_value=")]}'\n\n10\n" + json.dumps(rows)),
        )
        for handler in list(page._handlers["response"]):
            await asyncio.create_task(handler(response), context=Context())

    async def click(self, actual_page, target, **kwargs):
        route = SimpleNamespace(fallback=AsyncMock(), continue_=AsyncMock(), abort=AsyncMock())
        await asyncio.create_task(routes[0](route, request), context=Context())
        if mode == "foreign-refusal":
            await respond([bad], object())
        await respond(rows)
        if mode in (
            "queryless",
            "late",
            "foreign-refusal",
            "foreign-positive-own-positive",
            "foreign-waf-own-positive",
        ):
            if mode == "late":
                await respond([bad, ["wrb.fr", "YhhmEf", "[5]"]])
            final = SimpleNamespace(
                url=URL + "?rpcids=as29s",
                request=object(),
                text=AsyncMock(return_value=_frame("as29s", _record(3, VIDEO_URL))),
            )
            for handler in list(page._handlers["response"]):
                await handler(final)

    monkeypatch.setattr(composer.MigratedComposer, "_click", click)
    started = []
    handle = active_video_overrides.set(override)
    try:
        if mode in (
            "queryless",
            "late",
            "foreign-refusal",
            "foreign-positive-own-positive",
            "foreign-waf-own-positive",
        ):
            result = await composer.MigratedComposer().submit_and_observe(
                page, poll_timeout_s=0.2, on_started=started.append, project_id=P
            )
            assert result.media_id == MEDIA
            assert started[0].media_id == MEDIA
            assert override.terminal == "accepted"
        else:
            error = WafRejectionError if mode == "waf" else WireFormatError
            with pytest.raises(error):
                await composer.MigratedComposer().submit_and_observe(
                    page, poll_timeout_s=0.2, on_started=started.append, project_id=P
                )
            assert override.terminal == ("rejected" if mode == "waf" else "unknown")
        if mode == "foreign-positive-own-masked":
            assert override.known_media_ids == []
            assert override.known_workflow_ids == []
        if mode in (
            "mixed",
            "duplicate",
            "foreign-positive-own-positive",
            "foreign-waf-own-positive",
        ):
            assert override.known_media_ids == [MEDIA]
            assert override.known_workflow_ids == [WF]
        assert override.closed
        assert not routes and not page._handlers["response"] and not page._handlers["request"]
    finally:
        active_video_overrides.reset(handle)
