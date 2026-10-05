"""R11 HTTP family selection on controlled extension metadata, with no Google calls."""

from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from gflow_cli.api.native_extension import NativeExtensionUnknownError, extend_native_video
from gflow_cli.errors import ConfigurationError

P, M = (str(UUID(int=i)) for i in (1, 2))


def controlled_extension(monkeypatch):
    import gflow_cli.api.native_extension as module

    page = AsyncMock()
    page.evaluate.side_effect = TimeoutError()
    client = AsyncMock()
    client._checkout_page.return_value = page
    client._checkin_page = Mock()
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *_: {"media": [{"media_id": M, "kind": "video", "width": 720, "height": 1280}]},
    )

    async def metadata(_page, rpc, *_):
        return [None, None, None, 2] if rpc == "nzlxg" else []

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr(
        module,
        "parse_extension_models",
        lambda *_args, **_kwargs: [
            {"model_key": "lite", "family": "veo_3_1_lite", "credits": 10, "aspect_enums": [1, 2]},
            {
                "model_key": "fast-landscape",
                "family": "veo_3_1_fast",
                "credits": 20,
                "aspect_enums": [2],
            },
            {
                "model_key": "fast-portrait",
                "family": "veo_3_1_fast",
                "credits": 20,
                "aspect_enums": [1],
            },
            {
                "model_key": "quality",
                "family": "veo_3_1_quality",
                "credits": 100,
                "aspect_enums": [1],
            },
        ],
    )
    mint = AsyncMock(return_value="controlled-token")
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", mint)
    return client, page, mint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("family", "expected"),
    [("veo_3_1_fast", "fast-portrait"), ("veo_3_1_quality", "quality"), (None, "lite")],
)
async def test_exact_family_selection_preserves_source_aspect_and_existing_default(
    monkeypatch, family, expected
):
    client, page, _ = controlled_extension(monkeypatch)
    with pytest.raises(NativeExtensionUnknownError):
        await extend_native_video(
            client, project_id=P, media_id=M, prompt="Continue", model_family=family
        )
    assert page.evaluate.await_count == 1
    assert page.evaluate.call_args.args[1]["args"][0][0][2:4] == [expected, 1]


@pytest.mark.asyncio
async def test_absent_low_priority_family_refuses_before_mint_or_submission(monkeypatch):
    client, page, mint = controlled_extension(monkeypatch)
    with pytest.raises(ConfigurationError):
        await extend_native_video(
            client,
            project_id=P,
            media_id=M,
            prompt="Continue",
            model_family="veo_3_1_lite_lower_priority",
        )
    mint.assert_not_awaited()
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["", "omni_flash", "unknown-family", False])
async def test_invalid_family_refuses_before_browser(monkeypatch, family):
    client, _, _ = controlled_extension(monkeypatch)
    with pytest.raises(ConfigurationError):
        await extend_native_video(
            client, project_id=P, media_id=M, prompt="Continue", model_family=family
        )
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_family_and_exact_key_conflict_refuses_before_browser(monkeypatch):
    client, _, _ = controlled_extension(monkeypatch)
    with pytest.raises(ConfigurationError):
        await extend_native_video(
            client,
            project_id=P,
            media_id=M,
            prompt="Continue",
            model_key="lite",
            model_family="veo_3_1_fast",
        )
    client._checkout_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alias", "family"),
    [
        ("veo-3.1-fast", "veo_3_1_fast"),
        ("veo-3.1-lite-low-priority", "veo_3_1_lite_lower_priority"),
    ],
)
async def test_private_worker_forwards_canonical_family_to_shared_sdk(
    monkeypatch, tmp_path, alias, family
):
    import gflow_cli.selfhost.extension_worker as module

    manager = AsyncMock()
    monkeypatch.setattr(module, "FlowApiClient", Mock(return_value=manager))
    submit = AsyncMock()
    monkeypatch.setattr(module, "extend_native_video", submit)
    monkeypatch.setattr(module, "wait_native_extension", AsyncMock(return_value=[]))
    await module._run_extension(
        "pro2", P, {"mediaGenerationId": M, "prompt": "Continue", "model": alias}, tmp_path
    )
    assert submit.await_args.kwargs["model_family"] == family
    assert submit.await_args.kwargs["model_key"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["omni-flash", "unsupported", False, None])
async def test_worker_invalid_model_refuses_before_browser(monkeypatch, tmp_path, alias):
    import gflow_cli.selfhost.extension_worker as module

    browser = Mock()
    monkeypatch.setattr(module, "FlowApiClient", browser)
    with pytest.raises(ConfigurationError):
        await module._run_extension(
            "pro2", P, {"mediaGenerationId": M, "prompt": "Continue", "model": alias}, tmp_path
        )
    browser.assert_not_called()
