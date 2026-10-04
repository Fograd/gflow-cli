"""Native dispatch hooks and real audio acknowledgment acceptance without Google."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.native_captcha import native_captcha_provider
from gflow_cli.api.transports import native_voices as voice
from gflow_cli.errors import VoiceMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
@pytest.mark.parametrize("save_failure", [False, True])
async def test_audio_accepts_exact_preview_before_save_failure(monkeypatch, save_failure):
    import gflow_cli.api.transports.migrated_resources as resources

    monkeypatch.setattr(resources, "read_project_payload", AsyncMock(return_value=[]))
    events = []
    calls = []

    async def mint(page, action):
        return "a" * 40

    async def evaluate(script, params, **kwargs):
        rpc = params["rpc"]
        calls.append(rpc)
        if rpc == voice.PREVIEW_RPC:
            assert events == ["submitted"]
            payload = [[[M, P, W]], []]
        elif rpc == voice.SAVE_MEDIA_RPC:
            assert events == ["submitted", "accepted"]
            if save_failure:
                raise OSError("later save failed")
            payload = [M, P, W]
        else:
            payload = [W, None, None, ["Guide"], P]
        return {
            "status": 200,
            "text": ")]}'\n" + json.dumps([["wrb.fr", rpc, json.dumps(payload), None]]),
        }

    page = SimpleNamespace(url=f"https://flow.google.com/project/{P}", evaluate=evaluate)
    with native_captcha_provider(
        mint, project_id=P, action="AUDIO_GENERATION", observe=events.append
    ):
        if save_failure:
            with pytest.raises(VoiceMutationUnknownError):
                await voice.create_saved_voice(page, P, "Guide", "Charon", "Hello", "Warm")
        else:
            result = await voice.create_saved_voice(page, P, "Guide", "Charon", "Hello", "Warm")
            assert result["ref"] == M
    assert events == ["submitted", "accepted"]
    assert calls.count(voice.PREVIEW_RPC) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["reference", "extension", "promotion"])
async def test_single_native_video_dispatch_hook_on_uncertain_response(monkeypatch, case):
    # Reuse the existing concrete fresh ownership/model fixtures; spy on the new
    # telemetry hook separately so their generation/checkpoint assertions remain.
    if case == "reference":
        import gflow_cli.api.native_reference_video as module
        from tests.api.test_native_reference_video import (
            test_fresh_audio_caps_single_dispatch_checkpoint_and_unknown as exercise,
        )
    elif case == "extension":
        import gflow_cli.api.native_extension as module
        from tests.api.test_native_extension import (
            test_checkpoint_precedes_single_dispatch_and_failure_preserves_handles as exercise,
        )
    else:
        import gflow_cli.api.native_video_upscale as module
        from tests.api.test_native_video_upscale import (
            test_single_dispatch_unknown_preserves_existing_workflow as exercise,
        )
    submit = Mock()
    outcome = Mock()
    monkeypatch.setattr(module, "native_captcha_submission", submit)
    monkeypatch.setattr(module, "native_captcha_outcome", outcome)
    await exercise(monkeypatch)
    submit.assert_called_once_with()
    outcome.assert_not_called()


@pytest.mark.asyncio
async def test_native_edit_exact_ack_marks_acceptance(monkeypatch):
    import gflow_cli.api.native_video_edit as module
    from tests.api.test_native_video_edit import (
        test_dispatch_once_correlates_assigned_ids as exercise,
    )

    submit = Mock()
    outcome = Mock()
    monkeypatch.setattr(module, "native_captcha_submission", submit)
    monkeypatch.setattr(module, "native_captcha_outcome", outcome)
    await exercise(monkeypatch)
    submit.assert_called_once_with()
    outcome.assert_called_once_with("accepted")
