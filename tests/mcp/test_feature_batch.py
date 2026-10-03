from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import VoiceMutationUnknownError
from gflow_cli.mcp import tools
from gflow_cli.services import native_voices

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
async def test_saved_voice_create_dispatches_exact_controls(monkeypatch):
    operation = AsyncMock(return_value={"ref": M, "workflow_id": W, "project_id": P})
    monkeypatch.setattr(native_voices, "saved_voice_operation", operation)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_create_saved_voice(
        P, "Narrator", "Charon", "Short dialogue.", "Warm and calm"
    )
    assert result["status"] == "ok" and result["ref"] == M
    operation.assert_awaited_once_with(
        profile="fixture",
        operation="create",
        project_id=P,
        display_name="Narrator",
        preset_voice="Charon",
        dialog="Short dialogue.",
        performance="Warm and calm",
    )


@pytest.mark.asyncio
async def test_saved_voice_delete_requires_true_before_service(monkeypatch):
    operation = AsyncMock()
    monkeypatch.setattr(native_voices, "saved_voice_operation", operation)
    result = await tools.gflow_delete_saved_voice(P, M)
    assert result["status"] != "ok"
    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_voice_unknown_preserves_known_audio_identity(monkeypatch):
    operation = AsyncMock(
        side_effect=VoiceMutationUnknownError(project_id=P, phase="save", media_id=M, workflow_id=W)
    )
    monkeypatch.setattr(native_voices, "saved_voice_operation", operation)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_create_saved_voice(P, "Narrator", "Charon", "Hello", "Calm")
    assert result["error"]["known_media_ids"] == [M]
    assert result["error"]["workflow_ids"] == [W]
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_extension_invalid_count_stops_before_profile(monkeypatch):
    resolver = AsyncMock(side_effect=AssertionError("must validate first"))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolver)
    result = await tools.gflow_extend_native_video(P, M, "Continue", "model", count=0)
    assert result["status"] != "ok"
    resolver.assert_not_called()
