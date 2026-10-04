from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import native_voices as voice
from gflow_cli.errors import VoiceMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def setup(monkeypatch):
    import gflow_cli.api.transports.migrated_resources as resources

    monkeypatch.setattr(resources, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(voice, "_mint_audio_token", AsyncMock(return_value="private-test-token"))


@pytest.mark.asyncio
async def test_create_one_preview_then_distinct_saves(setup, monkeypatch):
    rpc = AsyncMock(side_effect=[[[[M, P, W]], []], [M, P, W], [W, None, None, ["Guide"], P]])
    monkeypatch.setattr(voice, "_rpc", rpc)
    result = await voice.create_saved_voice(None, P, "Guide", "Charon", "Hello", "Warm")
    assert result["ref"] == M and result["workflow_id"] == W
    assert [call.args[2] for call in rpc.await_args_list] == ["no0P6", "lt8g5", "mYWVGd"]


@pytest.mark.asyncio
async def test_save_failure_preserves_preview_identity_without_retry(setup, monkeypatch):
    rpc = AsyncMock(side_effect=[[[[M, P, W]], []], RuntimeError("private raw wire")])
    monkeypatch.setattr(voice, "_rpc", rpc)
    with pytest.raises(VoiceMutationUnknownError) as caught:
        await voice.create_saved_voice(None, P, "Guide", "Charon", "Hello", "Warm")
    problem = caught.value.to_problem_details()
    assert problem["known_media_ids"] == [M] and problem["workflow_ids"] == [W]
    assert problem["phase"] == "save" and caught.value.retryable is False
    assert "private raw wire" not in str(problem)
    assert rpc.await_count == 2


@pytest.mark.asyncio
async def test_cancel_after_preview_keeps_cancellation_and_handles(setup, monkeypatch):
    import asyncio

    rpc = AsyncMock(side_effect=[[[[M, P, W]], []], asyncio.CancelledError()])
    monkeypatch.setattr(voice, "_rpc", rpc)
    with pytest.raises(asyncio.CancelledError) as caught:
        await voice.create_saved_voice(None, P, "Guide", "Charon", "Hello", "Warm")
    typed = vars(caught.value)["gflow_saved_voice_unknown"]
    assert typed.to_problem_details()["known_media_ids"] == [M]


@pytest.mark.asyncio
async def test_delete_owned_saved_voice_exact_source_fields(monkeypatch):
    monkeypatch.setattr(voice, "get_saved_voice", AsyncMock(return_value={"workflow_id": W}))
    rpc = AsyncMock(return_value=[])
    monkeypatch.setattr(voice, "_rpc", rpc)
    result = await voice.delete_saved_voice(None, P, M, True)
    assert result["deleted"] == [M]
    assert rpc.await_args.args[2:] == ("cz8Z4b", [None, [W], P, None, None, None, [M]])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "PUBLIC_ERROR_USER_REQUESTS_THROTTLED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED",
        "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC",
        "PUBLIC_ERROR_MODEL_ACCESS_DENIED",
    ],
)
async def test_preview_unique_quota_is_terminal_not_unknown(setup, monkeypatch, reason):
    from types import SimpleNamespace

    from gflow_cli.errors import NativeQuotaError
    from tests.api.test_native_quota_producers import refusal

    page = SimpleNamespace(
        evaluate=AsyncMock(return_value={"status": 200, "text": refusal(voice.PREVIEW_RPC, reason)})
    )
    with pytest.raises(NativeQuotaError) as caught:
        await voice.create_saved_voice(page, P, "Guide", "Charon", "Hello", "Warm")
    assert caught.value.reason == reason
    assert caught.value.retryable is False
    page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_quota_during_save_preserves_already_accepted_preview(setup, monkeypatch):
    from gflow_cli.errors import NativeQuotaError

    rpc = AsyncMock(
        side_effect=[
            [[[M, P, W]], []],
            NativeQuotaError("PUBLIC_ERROR_USER_REQUESTS_THROTTLED", route="lt8g5"),
        ]
    )
    monkeypatch.setattr(voice, "_rpc", rpc)
    with pytest.raises(VoiceMutationUnknownError) as caught:
        await voice.create_saved_voice(None, P, "Guide", "Charon", "Hello", "Warm")
    assert caught.value.to_problem_details()["known_media_ids"] == [M]
    assert caught.value.to_problem_details()["phase"] == "save"
    assert rpc.await_count == 2
