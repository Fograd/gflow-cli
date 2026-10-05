"""Typed image quota rejects once; mixed records retain unknown checkpoints."""

import json
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ImageGenerationUnknownError, NativeQuotaError
from gflow_cli.selfhost.image_captcha_policy import run_with_image_captcha_policy
from tests.api.test_image_provider_dispatch import RoutedPage
from tests.api.test_native_quota_producers import refusal
from tests.api.transports.test_migrated_composer import _frame
from tests.api.transports.test_migrated_images import PROJECT, image_payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "PUBLIC_ERROR_USER_REQUESTS_THROTTLED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED",
        "PUBLIC_ERROR_MODEL_ACCESS_DENIED",
        "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC",
    ],
)
@pytest.mark.parametrize("mixed", [None, "masked", "accepted"])
async def test_image_quota_dispatch_once_without_waf_replay(tmp_path, monkeypatch, reason, mixed):
    from gflow_cli.selfhost.image_captcha_policy import ProviderKeys

    monkeypatch.setattr(ProviderKeys, "get", lambda *_: "synthetic-private-key")
    page = RoutedPage(url="https://flow.google.com/project/" + PROJECT)
    page.dom.prompt = "a blue cup"
    page.foreign = False
    page.reply = refusal("ogiZ0b", reason)
    if mixed == "masked":
        page.reply += "\n" + json.dumps([["wrb.fr", "ogiZ0b", None, None, None, [5], "generic"]])
    elif mixed == "accepted":
        page.reply += "\n" + _frame("ogiZ0b", image_payload())
    scopes, phases = [], []

    async def attempt(override):
        scopes.append(override)
        # Exercise actual routed composer; no external provider is called by this fixture.
        override.token = AsyncMock(return_value="replacement" * 5)
        override.observe = phases.append
        return await MigratedComposer().submit_images_and_observe(
            page, GenerateImageRequest(prompt="a blue cup"), project_id=PROJECT
        )

    expected = NativeQuotaError if mixed is None else ImageGenerationUnknownError
    with pytest.raises(expected) as caught:
        await run_with_image_captcha_policy(
            {"count": 1, "captchaRetry": 10}, PROJECT, tmp_path, attempt
        )
    assert len(scopes) == 1 and scopes[0].closed
    assert phases == ["submitted", "rejected" if mixed is None else "unknown"]
    assert page.cleaned and not page.listeners("response")
    if mixed is None:
        metadata = caught.value.to_problem_details()
        assert metadata["nativeReason"] == reason
        assert metadata["nativeOperation"] == "images"
        assert "nativeModelKey" not in metadata
    elif mixed == "accepted":
        assert caught.value.media_ids
