"""Every native operation wrapper uses the explicit refusal policy."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from gflow_cli.selfhost import native_captcha_policy as policy

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reference", "edit", "extension", "promotion", "voice"])
async def test_wrappers_forward_exact_policy_and_fresh_attempt(monkeypatch, tmp_path, kind):
    if kind == "reference":
        from gflow_cli.selfhost import reference_video_worker as module

        public = "run_reference_video"
        private = "_run_reference_video"
    elif kind == "edit":
        from gflow_cli.selfhost import native_video_edit_worker as module

        public = "run_edit"
        private = "_run_edit"
    elif kind == "extension":
        from gflow_cli.selfhost import extension_worker as module

        public = "run_extension"
        private = "_run_extension"
    elif kind == "promotion":
        from gflow_cli.selfhost import video_promotion_worker as module

        public = "run_promotion"
        private = "_run_promotion"
    else:
        from gflow_cli.selfhost import native_worker as module

        public = "execute"
        private = "_execute"
    original = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(module, private, original)
    seen = []

    async def controlled(payload, project, action, attempt):
        seen.append((payload, project, action))
        return await attempt()

    monkeypatch.setattr(policy, "run_with_native_captcha_policy", controlled)
    if kind == "promotion":
        monkeypatch.setattr(module, "run_with_native_captcha_policy", controlled)
    payload = {"captchaRetry": 3, "project_id": P}
    if kind == "voice":
        result = await module.execute("voice-saved-create", "pro1", payload)
        expected = ("voice-saved-create", "pro1", payload)
    else:
        result = await getattr(module, public)("pro1", P, payload, tmp_path)
        expected = ("pro1", P, payload, tmp_path)
    original.assert_awaited_once_with(*expected)
    assert result == {"ok": True}
    assert seen == [(payload, P, "AUDIO_GENERATION" if kind == "voice" else "VIDEO_GENERATION")]
