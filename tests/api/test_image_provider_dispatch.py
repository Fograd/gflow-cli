import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.api.transports.migrated_composer import MigratedComposer, _guard_image_submit
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.errors import ImageGenerationUnknownError, WafRejectionError
from tests.api.test_migrated_image_overrides import PROJECT as BODY_PROJECT
from tests.api.test_migrated_image_overrides import body
from tests.api.test_native_generation_refusal import refusal
from tests.api.transports.test_migrated_composer import FakePage, FakeResponse, _batch_url, _frame
from tests.api.transports.test_migrated_images import PROJECT, image_payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,method",
    [
        ("https://foreign.test/_/AiSandboxAngularFrontend/data/batchexecute", "POST"),
        ("https://flow.google.com/wrong", "POST"),
        ("http://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute", "POST"),
        ("https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute", "GET"),
    ],
)
async def test_wrong_endpoint_never_mints(url, method):
    mint = AsyncMock(return_value="replacement" * 5)
    override = ImageOverrides(PROJECT, 1, token=mint)
    route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
    raw = SimpleNamespace(url=url, method=method, post_data=body().replace(BODY_PROJECT, PROJECT))
    assert await _guard_image_submit(route, raw, (), None, override=override)
    mint.assert_not_called()
    route.continue_.assert_not_called()
    route.abort.assert_awaited_once()


class RoutedPage(FakePage):
    async def route(self, matcher, handler):
        self.handler = handler

    async def unroute(self, matcher, handler):
        self.cleaned = True

    def _fire_submit(self):
        async def dispatch():
            raw = SimpleNamespace(
                url=_batch_url("ogiZ0b"),
                method="POST",
                post_data=body().replace(BODY_PROJECT, PROJECT),
            )
            route = SimpleNamespace(abort=AsyncMock(), continue_=AsyncMock())
            await self.handler(route, raw)
            if route.abort.called:
                return
            response = FakeResponse(_batch_url("ogiZ0b"), self.reply)
            response.request = raw if not self.foreign else SimpleNamespace()
            self._fire_response(response)

        asyncio.create_task(dispatch())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply_kind",
    ["accepted", "refused", "mixed", "partial", "duplicate", "mixed-masked", "foreign"],
)
async def test_real_composer_dispatch_and_acknowledgement(reply_kind, monkeypatch):
    import gflow_cli.api.transports.migrated_composer as composer

    monkeypatch.setattr(composer, "IMAGE_REPLY_BUDGET_S", 0.5)
    page = RoutedPage(url="https://flow.google.com/project/" + PROJECT)
    page.dom.prompt = "a blue cup"
    payload = image_payload()
    if reply_kind == "duplicate":
        payload[0][0].append(payload[0][0][0])
    accepted = _frame("ogiZ0b", payload)
    page.reply = (
        refusal("ogiZ0b")
        if reply_kind == "refused"
        else accepted + "\n" + refusal("ogiZ0b")
        if reply_kind == "mixed"
        else accepted
    )
    if reply_kind == "mixed-masked":
        import json

        masked = json.dumps([["wrb.fr", "ogiZ0b", None, None, None, [5], "generic"]])
        page.reply = refusal("ogiZ0b") + "\n" + masked
    page.foreign = reply_kind == "foreign"
    phases = []
    override = ImageOverrides(
        PROJECT,
        2 if reply_kind in ("partial", "duplicate") else 1,
        token=AsyncMock(return_value="replacement" * 5),
        observe=phases.append,
    )
    if reply_kind in ("partial", "duplicate"):
        # Two requested outputs, one acknowledged; never retry positive partial work.
        original_body = body
        # Override body helper used by the page dispatch for this test only.
        monkeypatch.setattr(
            __import__(__name__, fromlist=["body"]), "body", lambda: original_body(2)
        )
    state = active_overrides.set(override)
    try:
        if reply_kind == "accepted":
            assert (
                len(
                    await MigratedComposer().submit_images_and_observe(
                        page, GenerateImageRequest(prompt="a blue cup"), project_id=PROJECT
                    )
                )
                == 1
            )
        else:
            expected = WafRejectionError if reply_kind == "refused" else ImageGenerationUnknownError
            with pytest.raises(expected) as caught:
                await MigratedComposer().submit_images_and_observe(
                    page, GenerateImageRequest(prompt="a blue cup"), project_id=PROJECT
                )
            if reply_kind in ("mixed", "partial", "duplicate"):
                assert caught.value.media_ids
    finally:
        override.close()
        active_overrides.reset(state)
    assert phases == [
        "submitted",
        "accepted"
        if reply_kind == "accepted"
        else "rejected"
        if reply_kind == "refused"
        else "unknown",
    ]
    assert page.cleaned
    assert not page.listeners("response")
