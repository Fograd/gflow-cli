from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.mcp import tools

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["extend", "edit", "reference"])
@pytest.mark.parametrize("failure", ["missing", "download", "cancel"])
async def test_native_video_recovery(tmp_path, monkeypatch, mode, failure):
    import asyncio
    import json

    from gflow_cli.api.native_extension import new_extension_started
    from gflow_cli.api.native_reference_video import new_reference_started

    started = new_reference_started(P, 1) if mode == "reference" else new_extension_started(P, M, 1)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    submit_name = {
        "extend": "extend_native_video",
        "edit": "edit_native_video",
        "reference": "generate_native_reference_video",
    }[mode]
    poll_name = {
        "extend": "wait_native_extension",
        "edit": "wait_native_video_edit",
        "reference": "wait_native_reference_video",
    }[mode]

    async def submit(**kwargs):
        await kwargs["on_started"](started)
        return started

    submit_mock = AsyncMock(side_effect=submit)
    setattr(client, submit_name, submit_mock)
    setattr(
        client,
        poll_name,
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    media_id=started.media_ids[0],
                    workflow_id=started.workflow_ids[0],
                    video_url=None if failure == "missing" else "https://example.invalid/video",
                )
            ]
        ),
    )
    client.download = AsyncMock(
        side_effect=(
            asyncio.CancelledError() if failure == "cancel" else OSError("private download error")
        )
    )
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: client)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    call = {
        "extend": lambda: tools.gflow_extend_native_video(
            P, M, "Continue", "model", out_dir=str(tmp_path)
        ),
        "edit": lambda: tools.gflow_edit_native_video(
            P, M, "Edit", "model", 120, out_dir=str(tmp_path)
        ),
        "reference": lambda: tools.gflow_generate_native_reference_video(
            P, "Create", image_ref=[M], out_dir=str(tmp_path)
        ),
    }[mode]
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await call()
    else:
        result = await call()
        assert result["error"]["outcome_unknown"] is True
        assert result["error"]["media_ids"] == list(started.media_ids)
        assert result["error"]["workflow_ids"] == list(started.workflow_ids)
        assert result["error"]["project_id"] == P
        assert result["error"]["retryable"] is False
    submit_mock.assert_awaited_once()
    forwarded = submit_mock.call_args.kwargs
    callback = forwarded.pop("on_started")
    assert callable(callback)
    expected = {
        "extend": dict(
            project_id=P,
            media_id=M,
            prompt="Continue",
            model_key="model",
            count=1,
            aspect=None,
            trim_start_frame=None,
            trim_end_frame=None,
        ),
        "edit": dict(
            project_id=P,
            media_id=M,
            prompt="Edit",
            model_key="model",
            start_frame=0,
            end_frame=120,
            image_ids=(),
            audio_ids=(),
            character_ids=(),
        ),
        "reference": dict(
            project_id=P,
            prompt="Create",
            reference_image_ids=(M,),
            reference_audio_ids=(),
            reference_character_ids=(),
            model_key=None,
            count=1,
            aspect="16:9",
            duration=None,
            resolution="720p",
        ),
    }[mode]
    assert forwarded == expected
    journals = list(tmp_path.glob("mcp-*-started-*.json"))
    assert len(journals) == 1
    record = json.loads(journals[0].read_text())
    assert record["media_ids"] == list(started.media_ids)
    assert record["workflow_ids"] == list(started.workflow_ids)
    assert journals[0].stat().st_mode & 0o777 == 0o600
