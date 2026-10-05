"""Public SDK service safely installs count-one policy and preserves defaults."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides
from gflow_cli.errors import ConfigurationError
from gflow_cli.services import video_captcha

P = "11111111-1111-4111-8111-111111111111"
TOKEN = "valid-private-test-token-" * 3


@pytest.mark.asyncio
async def test_sdk_supplied_token_scope_installed_and_closed(tmp_path):
    seen = []

    async def generate(**kw):
        override = active_video_overrides.get()
        seen.append(override)
        assert (
            await override.token(SimpleNamespace(url="https://flow.google.com/project/" + P))
            == TOKEN
        )
        return "result"

    client = SimpleNamespace(generate_video=generate, _uses_native_characters=lambda: True)
    assert (
        await video_captcha.generate_video_with_captcha(
            client,
            req=SimpleNamespace(count=1),
            project_id=P,
            captcha_token=TOKEN,
            root=tmp_path,
        )
        == "result"
    )
    assert seen[0].closed and active_video_overrides.get() is None


@pytest.mark.asyncio
async def test_sdk_default_preserves_ordinary_generate(tmp_path):
    generate = AsyncMock(return_value="default")
    client = SimpleNamespace(generate_video=generate)
    req = SimpleNamespace(count=1)
    assert (
        await video_captcha.generate_video_with_captcha(
            client, req=req, project_id=P, root=tmp_path, download=False
        )
        == "default"
    )
    generate.assert_awaited_once_with(req=req, project_id=P, download=False)


@pytest.mark.asyncio
async def test_sdk_legacy_host_controls_refuse_before_generation(tmp_path):
    generate = AsyncMock()
    client = SimpleNamespace(generate_video=generate, _uses_native_characters=lambda: False)
    with pytest.raises(ConfigurationError, match="native"):
        await video_captcha.generate_video_with_captcha(
            client, req=SimpleNamespace(count=1), project_id=P, captcha_retry=1, root=tmp_path
        )
    generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 3, 4])
async def test_sdk_plural_supplied_uses_batch_and_closes_scope(tmp_path, count):
    seen = []

    async def batch(**kw):
        override = active_video_overrides.get()
        assert override.count == count
        seen.append(override)
        return "all-results"

    singular = AsyncMock()
    client = SimpleNamespace(
        generate_video=singular, generate_videos_batch=batch, _uses_native_characters=lambda: True
    )
    result = await video_captcha.generate_video_with_captcha(
        client,
        req=SimpleNamespace(count=count),
        project_id=P,
        captcha_token=TOKEN,
        root=tmp_path,
        name_resolver=object(),
    )
    assert result == "all-results"
    singular.assert_not_awaited()
    assert seen[0].closed and active_video_overrides.get() is None
