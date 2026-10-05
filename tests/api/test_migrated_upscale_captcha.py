from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode

import pytest

from gflow_cli.api.transports.migrated_upscale_overrides import UpscaleOverride, rewrite_upscale
from gflow_cli.errors import WireFormatError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
TOKEN = "replacement-token-" * 3
URL = "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=SPrCad"


def body(*, project=P, media=M, enum=1, flag=1):
    ctx = [None] * 11
    ctx[5] = project
    ctx[10] = ["browser-token-" * 3, flag]
    return urlencode(
        {
            "f.req": json.dumps([[["SPrCad", json.dumps([media, enum, ctx]), None, "generic"]]]),
            "at": "preserved",
        }
    )


def test_rewrite_changes_only_token():
    original = body()
    changed = rewrite_upscale(original, project=P, media=M, token=TOKEN)
    before = json.loads(json.loads(parse_qs(original)["f.req"][0])[0][0][1])
    after = json.loads(json.loads(parse_qs(changed)["f.req"][0])[0][0][1])
    assert after[2][10][0] == TOKEN
    after[2][10][0] = before[2][10][0]
    assert after == before
    assert parse_qs(changed)["at"] == ["preserved"]


@pytest.mark.parametrize(
    "kwargs",
    [{"project": M}, {"media": P}, {"enum": True}, {"enum": 2}, {"flag": True}, {"flag": 2}],
)
def test_rewrite_refuses_unmeasured_envelope(kwargs):
    with pytest.raises(WireFormatError, match="envelope"):
        rewrite_upscale(body(**kwargs), project=P, media=M, token=TOKEN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,method", [("https://example.test/batchexecute?rpcids=SPrCad", "POST"), (URL, "GET")]
)
async def test_guard_refuses_foreign_endpoint(url, method):
    route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
    request = SimpleNamespace(url=url, method=method, post_data=body())
    override = UpscaleOverride(project=P, media=M, token=TOKEN)
    with pytest.raises(WireFormatError):
        await override.guard(route, request)
    route.abort.assert_awaited_once()
    route.continue_.assert_not_awaited()
    assert not override.dispatched


@pytest.mark.asyncio
async def test_one_use_dispatch():
    route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
    request = SimpleNamespace(url=URL, method="POST", post_data=body())
    override = UpscaleOverride(project=P, media=M, token=TOKEN)
    await override.guard(route, request)
    assert override.dispatched
    with pytest.raises(WireFormatError, match="replay"):
        await override.guard(route, request)
    assert route.continue_.await_count == 1


@pytest.mark.asyncio
async def test_active_4k_disabled_refuses_before_provider_mint(monkeypatch):
    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.api.native_captcha import native_captcha_provider
    from gflow_cli.api.transports import migrated_upscale as transport
    from gflow_cli.errors import UpscaleUnavailableError

    mint = AsyncMock()
    page = SimpleNamespace(url="", wait_for_timeout=AsyncMock())

    async def goto(url, **kwargs):
        page.url = url

    page.goto = AsyncMock(side_effect=goto)
    download = SimpleNamespace(click=AsyncMock())
    target = SimpleNamespace(is_disabled=AsyncMock(return_value=True))
    page.wait_for_selector = AsyncMock(side_effect=[download, target, download, target])
    monkeypatch.setattr(
        transport,
        "lookup_asset",
        AsyncMock(return_value=SimpleNamespace(project_id=P, media_id=M, kind="image")),
    )
    with native_captcha_provider(mint, project_id=P, action="IMAGE_GENERATION"):
        with pytest.raises(UpscaleUnavailableError, match="4K"):
            await transport.upscale_image_migrated(
                page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_4K
            )
    mint.assert_not_awaited()
    assert page.goto.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        "accepted",
        "waf",
        "ambiguous",
        "malformed-image",
        "dispatch-cancel",
        "dispatch-error",
        "masked-waf",
        "queryless",
        "duplicate-positive",
    ],
)
async def test_active_upscale_consumes_on_homepage_correlates_exact_request_and_cleans(outcome):
    import base64
    from contextvars import Context
    from unittest.mock import patch

    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.api.native_captcha import native_captcha_provider
    from gflow_cli.api.transports import migrated_upscale as transport
    from gflow_cli.api.transports.migrated_upscale import upscale_image_migrated

    events = []
    routes = []
    listeners = []
    page = SimpleNamespace(url="", wait_for_timeout=AsyncMock(), evaluate=AsyncMock())

    async def goto(url, **kwargs):
        page.url = url

    page.goto = AsyncMock(side_effect=goto)

    async def mint(actual_page, action):
        assert actual_page.url == "https://flow.google.com/project/" + P
        assert action == "IMAGE_GENERATION"
        return TOKEN

    png = b"\x89PNG\r\n\x1a\n" + b"test"
    encoded = base64.b64encode(png).decode()
    if outcome == "malformed-image":
        encoded = "not-valid-base64"
    rows = [["wrb.fr", "SPrCad", json.dumps([[], encoded])]]
    if outcome in ("waf", "ambiguous", "masked-waf"):
        refusal = [
            "wrb.fr",
            "SPrCad",
            None,
            None,
            None,
            [
                7,
                None,
                [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]],
            ],
        ]
        rows = [refusal] + (rows if outcome == "ambiguous" else [])
        if outcome == "masked-waf":
            rows.append(["wrb.fr", "SPrCad", json.dumps([5])])
    if outcome == "duplicate-positive":
        rows += rows
    response_body = ")]}'\n\n123\n" + json.dumps(rows)

    async def click():
        request_url = URL.split("?")[0] if outcome == "queryless" else URL
        request = SimpleNamespace(url=request_url, method="POST", post_data=body())
        route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
        if outcome in ("dispatch-cancel", "dispatch-error"):
            import asyncio

            error = (
                asyncio.CancelledError() if outcome == "dispatch-cancel" else RuntimeError("lost")
            )
            route.continue_.side_effect = error
        import asyncio

        await asyncio.create_task(routes[0](route, request), context=Context())
        response = SimpleNamespace(
            url=request_url, request=request, text=AsyncMock(return_value=response_body)
        )
        # An unrelated response with an identical body must not win acknowledgment.
        unrelated = SimpleNamespace(
            url=URL,
            request=SimpleNamespace(post_data=body()),
            text=AsyncMock(return_value=response_body),
        )
        await asyncio.create_task(listeners[0](unrelated), context=Context())
        unrelated.text.assert_not_awaited()
        await asyncio.create_task(listeners[0](response), context=Context())
        rewritten = route.continue_.await_args.kwargs["post_data"]
        assert TOKEN in json.loads(json.loads(parse_qs(rewritten)["f.req"][0])[0][0][1])[2][10]

    download = SimpleNamespace(click=AsyncMock())
    target = SimpleNamespace(
        click=AsyncMock(side_effect=click),
        is_disabled=AsyncMock(return_value=False),
        get_attribute=AsyncMock(return_value=None),
    )
    page.wait_for_selector = AsyncMock(side_effect=[download, target, download, target])

    async def install(pattern, handler):
        if outcome == "queryless":
            from playwright._impl._helper import url_matches

            assert url_matches(None, URL.split("?")[0], pattern)
        routes.append(handler)

    async def remove(pattern, handler):
        routes.remove(handler)

    page.route = AsyncMock(side_effect=install)
    page.unroute = AsyncMock(side_effect=remove)
    page.on = lambda event, handler: listeners.append(handler)
    page.remove_listener = lambda event, handler: listeners.remove(handler)
    owned = SimpleNamespace(media_id=M, project_id=P, kind="image")
    with (
        patch.object(transport, "lookup_asset", AsyncMock(return_value=owned), create=True),
        native_captcha_provider(
            mint, project_id=P, action="IMAGE_GENERATION", observe=events.append
        ),
    ):
        if outcome in ("accepted", "queryless"):
            result = await upscale_image_migrated(
                page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_2K
            )
            assert result == png
        else:
            import asyncio

            from gflow_cli.errors import WafRejectionError

            expected = {
                "waf": WafRejectionError,
                "dispatch-cancel": asyncio.CancelledError,
                "dispatch-error": RuntimeError,
            }.get(outcome, WireFormatError)
            with pytest.raises(expected):
                await upscale_image_migrated(
                    page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_2K
                )
    terminal = {
        "accepted": "accepted",
        "waf": "rejected",
        "ambiguous": "unknown",
        "masked-waf": "unknown",
        "queryless": "accepted",
        "duplicate-positive": "unknown",
        "malformed-image": "accepted",
        "dispatch-cancel": "unknown",
        "dispatch-error": "unknown",
    }[outcome]
    assert events == ["submitted", terminal]
    assert not routes and not listeners


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", ["foreign", "video", "missing"])
async def test_active_wrong_media_refuses_before_paid_mint(monkeypatch, proof):
    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.api.native_captcha import native_captcha_provider
    from gflow_cli.api.transports import migrated_upscale as transport

    page = SimpleNamespace(url="", goto=AsyncMock())

    async def goto(url, **kwargs):
        page.url = url

    page.goto.side_effect = goto
    owned = SimpleNamespace(
        media_id=M,
        project_id=M if proof == "foreign" else P,
        kind="video" if proof == "video" else "image",
    )
    lookup = AsyncMock(return_value=owned)
    if proof == "missing":
        lookup.side_effect = ValueError("missing")
    monkeypatch.setattr(transport, "lookup_asset", lookup, raising=False)
    mint = AsyncMock(return_value=TOKEN)
    with native_captcha_provider(mint, project_id=P, action="IMAGE_GENERATION"):
        with pytest.raises((ValueError, WireFormatError)):
            await transport.upscale_image_migrated(
                page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_2K
            )
    mint.assert_not_awaited()
    assert page.goto.await_count == 1


def test_response_match_requires_exact_project_context_slot():
    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.api.transports.migrated_upscale import matches_upscale_request

    original = body(project=M)
    fields = parse_qs(original)
    frames = json.loads(fields["f.req"][0])
    args = json.loads(frames[0][0][1])
    args[2][0] = P  # unrelated cell must not establish ownership
    frames[0][0][1] = json.dumps(args)
    assert not matches_upscale_request(
        urlencode({"f.req": json.dumps(frames)}),
        media_id=M,
        project_id=P,
        target_resolution=TargetResolution.RES_2K,
    )


@pytest.mark.asyncio
async def test_browser_once_requires_fresh_owned_image(monkeypatch):
    from gflow_cli.api.image_upscale import TargetResolution
    from gflow_cli.api.transports import migrated_upscale as module

    monkeypatch.setattr(module, "native_captcha_active", lambda: False)
    monkeypatch.setattr(
        module,
        "lookup_asset",
        AsyncMock(return_value=SimpleNamespace(media_id=M, project_id=M, kind="image")),
    )
    menu = AsyncMock(side_effect=WireFormatError(detail="menu reached"))
    monkeypatch.setattr(module, "_upscale_menu", menu)
    page = SimpleNamespace(goto=AsyncMock())
    with pytest.raises(WireFormatError, match="owned image"):
        await module.upscale_image_migrated(
            page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_2K
        )
    menu.assert_not_awaited()
