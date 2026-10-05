"""Actual transport/worker policy composition; no browser or provider calls."""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import contextmanager
from contextvars import Context
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.api.native_captcha import native_captcha_provider
from gflow_cli.api.transports import migrated_upscale as transport
from gflow_cli.api.transports.migrated_upscale_overrides import rewrite_upscale
from gflow_cli.errors import (
    NativeQuotaError,
    TransportTimeoutError,
    UiSelectorDriftError,
    UpscaleUnavailableError,
    WafRejectionError,
    WireFormatError,
)
from gflow_cli.selfhost import image_upscale_worker as worker
from tests.api.test_migrated_upscale_captcha import URL, M, P, body

PNG = b"\x89PNG\r\n\x1a\n" + b"test"


class Page:
    def __init__(self, outcome="accepted", *, resolution=TargetResolution.RES_2K, menu_states=()):
        self.url = ""
        self.outcome = outcome
        self.resolution = resolution
        self.menu_states = list(menu_states)
        self.menu_reads = 0
        self.trace = []
        self.routes = []
        self.listeners = []
        self.history = []
        self.before_response = None
        self.forwarded = []
        self.wait_for_timeout = AsyncMock()
        self.evaluate = AsyncMock()

    async def goto(self, url, **kwargs):
        self.url = url
        self.trace.append(("goto", url))

    async def wait_for_selector(self, selector, **kwargs):
        if "download" in selector:
            return SimpleNamespace(click=AsyncMock())
        assert ("4K" if self.resolution is TargetResolution.RES_4K else "2K") in selector
        self.menu_reads += 1
        self.trace.append(("menu", self.menu_reads))
        state = self.menu_states.pop(0) if self.menu_states else "enabled"
        if state == "missing":
            raise PlaywrightTimeoutError("missing")
        return SimpleNamespace(
            click=AsyncMock(side_effect=self.dispatch),
            is_disabled=AsyncMock(return_value=state == "disabled"),
            get_attribute=AsyncMock(return_value="true" if state == "aria-disabled" else None),
        )

    async def route(self, pattern, handler):
        self.routes.append(handler)

    async def unroute(self, pattern, handler):
        self.routes.remove(handler)

    def on(self, event, handler):
        self.listeners.append(handler)
        self.history.append(handler)

    def remove_listener(self, event, handler):
        self.listeners.remove(handler)

    async def dispatch(self):
        enum = 2 if self.resolution is TargetResolution.RES_4K else 1
        if self.outcome == "wrong-enum":
            enum = 1
        request = SimpleNamespace(url=URL, method="POST", post_data=body(enum=enum))

        async def forward(**kwargs):
            self.forwarded.append(kwargs["post_data"])
            if self.outcome == "cancel":
                raise asyncio.CancelledError()

        route = SimpleNamespace(continue_=AsyncMock(side_effect=forward), abort=AsyncMock())
        if self.routes:
            await asyncio.create_task(self.routes[0](route, request), context=Context())
        else:
            self.forwarded.append(request.post_data)
        if not self.forwarded or self.outcome == "timeout":
            return
        if self.before_response is not None:
            await self.before_response()
        encoded = (
            "invalid-base64" if self.outcome == "invalid-bytes" else base64.b64encode(PNG).decode()
        )
        positive = ["wrb.fr", "SPrCad", json.dumps([[], encoded])]
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
        traffic = [
            "wrb.fr",
            "SPrCad",
            None,
            None,
            None,
            [
                8,
                None,
                [
                    [
                        "type.googleapis.com/google.rpc.ErrorInfo",
                        ["PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC"],
                    ]
                ],
            ],
        ]
        if "enum" in self.outcome:
            traffic[5][2][0] = [
                "type.googleapis.com/google.internal.labs.aisandbox.proto.common.v1.PublicAitkError",
                [50],
            ]
        rows = [positive]
        if self.outcome == "waf":
            rows = [refusal]
        elif self.outcome == "mixed":
            rows = [refusal, positive]
        elif self.outcome == "masked-null":
            rows = [refusal, ["wrb.fr", "SPrCad", None, None, None, [5]]]
        elif self.outcome == "duplicate":
            rows = [positive, positive]
        elif self.outcome.startswith("traffic"):
            rows = [traffic]
            if self.outcome.endswith("mixed"):
                rows.append(positive)
            elif self.outcome.endswith("masked"):
                rows.append(["wrb.fr", "SPrCad", None, None, None, [5]])
        elif self.outcome == "timeout":
            rows = []
        response = SimpleNamespace(
            url=URL,
            request=request,
            text=AsyncMock(return_value=")]}'\n\n123\n" + json.dumps(rows)),
        )
        self.last_response = response
        for handler in list(self.listeners):
            await asyncio.create_task(handler(response), context=Context())


@pytest.fixture
def state(tmp_path, monkeypatch):
    from gflow_cli.selfhost import native_captcha, native_provider

    seen = SimpleNamespace(events=[], tokens=[], pages=[], scopes=[], proofs=[], mint_pages=[])
    monkeypatch.setattr(native_captcha, "environment_root", lambda: tmp_path)
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))

    @contextmanager
    def scope(payload, project, action, *, root):
        assert project == P and action == "IMAGE_GENERATION"
        assert payload.get("captchaRetry", 1) == 1
        if payload.get("captchaOrder") is None and payload.get("captchaRetry") is None:
            yield
            return
        seen.scopes.append(dict(payload))

        async def mint(page, mint_action):
            assert page.url == "https://flow.google.com/project/" + P
            page.trace.append(("mint", page.url))
            seen.mint_pages.append(page)
            token = "fresh-test-token-" * 3 + str(len(seen.tokens))
            seen.tokens.append(token)
            return token

        with native_captcha_provider(mint, project_id=P, action=action, observe=seen.events.append):
            yield

    monkeypatch.setattr(native_provider, "native_provider_context", scope)

    async def owned(page, *, project_id, media_id):
        assert page.url == "https://flow.google.com/project/" + P
        assert project_id == P and media_id == M
        seen.proofs.append(page)
        return SimpleNamespace(project_id=P, media_id=M, kind="image")

    monkeypatch.setattr(transport, "lookup_asset", owned)
    monkeypatch.setattr(worker, "_make_provider_dir", lambda profile: tmp_path)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(headless=True))
    return seen


async def run_worker(
    tmp_path,
    monkeypatch,
    state,
    *,
    outcomes,
    retry=3,
    resolution="2k",
    supplied=False,
    late_callback=False,
):
    target = TargetResolution.from_cli(resolution)
    remaining = list(outcomes)

    class Client:
        def __init__(self, **kwargs):
            self.page = Page(remaining.pop(0), resolution=target)
            state.pages.append(self.page)
            if late_callback and len(state.pages) > 1:
                previous = state.pages[-2]

                async def late():
                    # Old exact-request refusal callback runs after new dispatch.
                    await previous.history[0](previous.last_response)

                self.page.before_response = late

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            assert not self.page.routes and not self.page.listeners

        async def upsample_image(self, **kwargs):
            assert kwargs["media_id"] == M and kwargs["project_id"] == P
            result = await transport.upscale_image_migrated(
                self.page, project_id=P, media_id=M, target_resolution=target, timeout_s=0.1
            )
            if self.page.outcome == "save-waf":
                raise WafRejectionError()
            if self.page.outcome == "save-error":
                Path(kwargs["out_path"]).write_bytes(b"partial")
                raise OSError("synthetic save failure")
            Path(kwargs["out_path"]).write_bytes(result)

    monkeypatch.setattr(worker, "FlowApiClient", Client)
    payload = {
        "resolution": resolution,
        "mediaGenerationId": M,
    }
    if retry is not None:
        payload.update(captchaRetry=retry, captchaOrder="CapSolver,2Captcha")
    if supplied:
        directory = tmp_path / "captcha-input"
        directory.mkdir()
        secret = directory / ("a" * 64 + ".token")
        secret.write_text("supplied-test-token-" * 3)
        secret.chmod(0o600)
        payload["captchaSecret"] = str(secret)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload))
    await worker.upscale("pro1", P, path)


def test_selected_4k_enum2_preserves_every_non_token_field():
    before = body(enum=2)
    after = rewrite_upscale(
        before,
        project=P,
        media=M,
        token="replacement-token-" * 3,
        target_resolution=TargetResolution.RES_4K,
    )
    before_frame = json.loads(parse_qs(before)["f.req"][0])
    after_frame = json.loads(parse_qs(after)["f.req"][0])
    before_args = json.loads(before_frame[0][0][1])
    after_args = json.loads(after_frame[0][0][1])
    after_args[2][10][0] = before_args[2][10][0]
    assert after_args == before_args
    after_frame[0][0][1] = before_frame[0][0][1]
    assert after_frame == before_frame
    assert parse_qs(before)["at"] == parse_qs(after)["at"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "states,expected",
    [
        (["disabled"], UpscaleUnavailableError),
        (["aria-disabled"], UpscaleUnavailableError),
        (["missing"], UiSelectorDriftError),
        (["enabled", "disabled"], UpscaleUnavailableError),
    ],
)
async def test_active_4k_fresh_menu_gate_and_recheck_before_dispatch(state, states, expected):
    page = Page(resolution=TargetResolution.RES_4K, menu_states=states)
    from gflow_cli.selfhost.native_captcha import private_native_captcha

    with private_native_captcha({"captchaRetry": 1}, P, "IMAGE_GENERATION"):
        with pytest.raises(expected):
            await transport.upscale_image_migrated(
                page, project_id=P, media_id=M, target_resolution=TargetResolution.RES_4K
            )
    assert len(state.tokens) == (1 if len(states) == 2 else 0)
    assert page.forwarded == []
    assert state.proofs == [page]
    assert page.menu_reads == len(states)


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["2k", "4k"])
async def test_actual_worker_policy_two_refusals_then_acceptance_fresh_clients(
    tmp_path, monkeypatch, state, resolution
):
    await run_worker(
        tmp_path, monkeypatch, state, outcomes=["waf", "waf", "accepted"], resolution=resolution
    )
    assert len(state.pages) == len(state.proofs) == len(state.tokens) == 3
    assert len({id(page) for page in state.pages}) == 3
    assert len(set(state.tokens)) == 3
    assert state.events == ["submitted", "rejected"] * 2 + ["submitted", "accepted"]
    assert all(
        scope["captchaRetry"] == 1 and scope["captchaOrder"] == "CapSolver,2Captcha"
        for scope in state.scopes
    )
    assert (tmp_path / "upscaled.png").read_bytes() == PNG
    if resolution == "4k":
        for page in state.pages:
            assert page.menu_reads == 2
            assert [entry[0] for entry in page.trace] == [
                "goto",
                "goto",
                "menu",
                "goto",
                "mint",
                "goto",
                "menu",
            ]
            args = json.loads(json.loads(parse_qs(page.forwarded[0])["f.req"][0])[0][0][1])
            assert args[1] == 2


@pytest.mark.asyncio
async def test_ten_explicit_rejections_exhaust_without_output(tmp_path, monkeypatch, state):
    with pytest.raises(WafRejectionError):
        await run_worker(tmp_path, monkeypatch, state, outcomes=["waf"] * 10, retry=10)
    assert len(state.pages) == 10
    assert state.events == ["submitted", "rejected"] * 10
    assert not (tmp_path / "upscaled.png").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected,terminal",
    [
        ("mixed", WireFormatError, "unknown"),
        ("masked-null", WireFormatError, "unknown"),
        ("duplicate", WireFormatError, "unknown"),
        ("invalid-bytes", WireFormatError, "accepted"),
        ("timeout", TransportTimeoutError, "unknown"),
        ("cancel", asyncio.CancelledError, "unknown"),
        ("save-waf", WafRejectionError, "accepted"),
        ("save-error", OSError, "accepted"),
    ],
)
async def test_uncertain_or_accepted_late_failure_never_replays(
    tmp_path, monkeypatch, state, outcome, expected, terminal
):
    with pytest.raises(expected):
        await run_worker(tmp_path, monkeypatch, state, outcomes=[outcome], retry=10)
    assert len(state.pages) == len(state.tokens) == 1
    assert state.events == ["submitted", terminal]


@pytest.mark.asyncio
async def test_real_supplied_secret_control_conflict_refuses_before_browser(
    tmp_path, monkeypatch, state
):
    with pytest.raises(ValueError, match="combined"):
        await run_worker(tmp_path, monkeypatch, state, outcomes=["waf"], retry=10, supplied=True)
    assert state.pages == [] and state.tokens == []
    assert len(list((tmp_path / "captcha-input").iterdir())) == 1


@pytest.mark.asyncio
async def test_real_supplied_secret_consumed_once_no_provider_mint(tmp_path, monkeypatch, state):
    from gflow_cli.selfhost.captcha import CaptchaStats

    with pytest.raises(WafRejectionError):
        await run_worker(tmp_path, monkeypatch, state, outcomes=["waf"], retry=None, supplied=True)
    assert len(state.pages) == 1
    assert state.tokens == []
    assert list((tmp_path / "captcha-input").iterdir()) == []
    assert CaptchaStats(tmp_path).public()["providers"]["supplied"] == {
        "submitted": 1,
        "rejected": 1,
    }


@pytest.mark.parametrize("enum", [1, True, 3, "2"])
def test_selected_4k_refuses_wrong_or_noninteger_enum(enum):
    with pytest.raises(WireFormatError):
        rewrite_upscale(
            body(enum=enum),
            project=P,
            media=M,
            token="replacement-token-" * 3,
            target_resolution=TargetResolution.RES_4K,
        )


@pytest.mark.asyncio
async def test_wrong_4k_enum_stops_without_google_dispatch_or_retry(tmp_path, monkeypatch, state):
    with pytest.raises(WireFormatError):
        await run_worker(
            tmp_path, monkeypatch, state, outcomes=["wrong-enum"], resolution="4k", retry=10
        )
    assert len(state.pages) == len(state.tokens) == 1
    assert state.pages[0].forwarded == []
    assert state.events == []


@pytest.mark.asyncio
async def test_old_refusal_callback_cannot_mark_fresh_attempt_rejected(
    tmp_path, monkeypatch, state
):
    await run_worker(
        tmp_path, monkeypatch, state, outcomes=["waf", "accepted"], retry=10, late_callback=True
    )
    assert len(state.pages) == len(state.tokens) == 2
    assert state.events == ["submitted", "rejected", "submitted", "accepted"]
    assert (tmp_path / "upscaled.png").read_bytes() == PNG


@pytest.mark.asyncio
async def test_unknown_selected_resolution_refuses_before_navigation_or_paid_mint(state):
    from gflow_cli.selfhost.native_captcha import private_native_captcha

    page = Page()
    with private_native_captcha({"captchaRetry": 1}, P, "IMAGE_GENERATION"):
        with pytest.raises(WireFormatError, match="unknown resolution"):
            await transport.upscale_image_migrated(
                page, project_id=P, media_id=M, target_resolution=True
            )
    assert page.trace == []
    assert state.proofs == []
    assert state.tokens == []


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["2k", "4k"])
@pytest.mark.parametrize("outcome", ["traffic", "traffic-enum"])
async def test_traffic_refusal_default_browser_is_terminal_without_decoding_bytes(
    resolution, outcome
):
    page = Page(outcome, resolution=TargetResolution.from_cli(resolution))
    with pytest.raises(NativeQuotaError) as caught:
        await transport.upscale_image_migrated(
            page,
            project_id=P,
            media_id=M,
            target_resolution=TargetResolution.from_cli(resolution),
            timeout_s=0.1,
        )
    assert caught.value.reason == "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC"
    assert len(page.forwarded) == 1
    assert not page.routes and not page.listeners


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["2k", "4k"])
@pytest.mark.parametrize("outcome", ["traffic", "traffic-enum"])
async def test_traffic_refusal_provider_retry10_is_one_terminal_rejected_attempt(
    tmp_path, monkeypatch, state, resolution, outcome
):
    with pytest.raises(NativeQuotaError) as caught:
        await run_worker(
            tmp_path, monkeypatch, state, outcomes=[outcome], retry=10, resolution=resolution
        )
    assert caught.value.reason == "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC"
    assert len(state.pages) == len(state.tokens) == 1
    assert state.events == ["submitted", "rejected"]
    assert not (tmp_path / "upscaled.png").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["traffic-mixed", "traffic-masked", "traffic-enum-mixed", "traffic-enum-masked"]
)
async def test_traffic_with_ack_or_masked_sibling_is_unknown_never_replayed(
    tmp_path, monkeypatch, state, outcome
):
    with pytest.raises(WireFormatError):
        await run_worker(tmp_path, monkeypatch, state, outcomes=[outcome], retry=10)
    assert len(state.pages) == len(state.tokens) == 1
    assert state.events == ["submitted", "unknown"]
    assert not (tmp_path / "upscaled.png").exists()
