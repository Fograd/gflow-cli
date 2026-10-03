"""Registered native CAPTCHA controls install the shared confidential scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.native_extension import new_extension_started
from gflow_cli.api.native_reference_video import new_reference_started
from gflow_cli.api.native_video_edit import NativeVideoEditStarted
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.mcp import tools

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
TOKEN = "synthetic-native-captcha-private-token"


@pytest.mark.parametrize(
    "name",
    [
        "gflow_create_saved_voice",
        "gflow_extend_native_video",
        "gflow_edit_native_video",
        "gflow_generate_native_reference_video",
    ],
)
def test_registered_token_input(name):
    tool = tools.server._tool_manager.get_tool(name)
    assert "captcha_token" in tool.fn_metadata.arg_model.model_fields


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["extend", "edit", "reference", "voice"])
async def test_direct_mcp_consumes_scope_without_returning_token(tmp_path, monkeypatch, kind):
    async def consume():
        page = SimpleNamespace(url="https://flow.google.com/project/" + P, evaluate=AsyncMock())
        assert (
            await TokenMinter(page).mint(
                "AUDIO_GENERATION" if kind == "voice" else "VIDEO_GENERATION"
            )
            == TOKEN
        )
        page.evaluate.assert_not_awaited()

    if kind == "voice":

        async def saved(*args, **kwargs):
            await consume()
            return {"status": "ok"}

        monkeypatch.setattr(tools, "_saved_voice_tool", saved)
        result = await tools.gflow_create_saved_voice(
            P, "Fixture", "Charon", "Hello", "Calm", captcha_token=TOKEN
        )
    else:
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        started = (
            new_reference_started(P, 1)
            if kind == "reference"
            else NativeVideoEditStarted(**vars(new_extension_started(P, M, 1)), end_frame=24)
            if kind == "edit"
            else new_extension_started(P, M, 1)
        )

        async def submit(**kwargs):
            await consume()
            return started

        setattr(
            client,
            {
                "extend": "extend_native_video",
                "edit": "edit_native_video",
                "reference": "generate_native_reference_video",
            }[kind],
            AsyncMock(side_effect=submit),
        )
        setattr(
            client,
            {
                "extend": "wait_native_extension",
                "edit": "wait_native_video_edit",
                "reference": "wait_native_reference_video",
            }[kind],
            AsyncMock(return_value=()),
        )
        monkeypatch.setattr(tools, "FlowApiClient", lambda **_: client)
        monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
        monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
        if kind == "reference":
            result = await tools.gflow_generate_native_reference_video(
                P, "Use", image_ref=[M], out_dir=str(tmp_path), captcha_token=TOKEN
            )
        elif kind == "edit":
            result = await tools.gflow_edit_native_video(
                P, M, "Edit", "key", 24, out_dir=str(tmp_path), captcha_token=TOKEN
            )
        else:
            result = await tools.gflow_extend_native_video(
                P, M, "Extend", "key", out_dir=str(tmp_path), captcha_token=TOKEN
            )
    assert result["status"] == "ok" and TOKEN not in str(result)
