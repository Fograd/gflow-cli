"""Private generic worker uses the same video DTO, without live Google calls."""

import json
from types import SimpleNamespace

import pytest

from gflow_cli.api.native_captcha import native_captcha_token
from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides
from gflow_cli.selfhost import general_video_worker as worker

P = "00000000-0000-4000-8000-000000000001"
M = "00000000-0000-4000-8000-000000000002"
W = "00000000-0000-4000-8000-000000000003"


@pytest.mark.asyncio
async def test_private_worker_token_callback_works_in_separate_context(tmp_path, monkeypatch):
    import contextvars

    seen = []

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_video(self, req, **kw):
            override = active_video_overrides.get()
            assert override is not None
            callback = contextvars.Context().run(
                override.token, SimpleNamespace(url=f"https://flow.google.com/project/{P}")
            )
            # The callback owns the copied context even in another Playwright task.
            import asyncio

            seen.append(await asyncio.create_task(callback, context=contextvars.Context()))
            await kw["on_started"](SimpleNamespace(media_id=M, workflow_id=W, flow_operation_id=W))
            return SimpleNamespace(
                status=SimpleNamespace(media_id=M), local_path=tmp_path / "video.mp4"
            )

    monkeypatch.setattr(worker, "FlowApiClient", Client)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(headless=True))
    monkeypatch.setattr(worker, "_make_provider_dir", lambda _: tmp_path)
    monkeypatch.setattr(
        worker.json_output,
        "video_result",
        lambda **kw: {"status": "ok", "media_id": M, "local_path": str(tmp_path / "video.mp4")},
    )
    monkeypatch.setattr(worker.json_output, "emit", lambda value: seen.append(value))
    with native_captcha_token(
        "supplied-private-token-abcdefghijklmnopqrstuvwxyz", project_id=P, action="VIDEO_GENERATION"
    ):
        await worker.generate_payload(
            "pro1", P, tmp_path, {"prompt": "test", "aspectRatio": "16:9", "count": 1}
        )
    assert seen[0].startswith("supplied-private")
    assert seen[1]["captchaProvider"] == "supplied"
    assert active_video_overrides.get() is None
    checkpoint = json.loads((tmp_path / "video-checkpoint.json").read_text())
    assert checkpoint["media_ids"] == [M] and checkpoint["workflow_ids"] == [W]
    assert "token" not in json.dumps(checkpoint)
    assert (tmp_path / "video-checkpoint.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_seed_refuses_before_client(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="seed"):
        await worker.generate_payload(
            "pro1", P, tmp_path, {"prompt": "test", "aspectRatio": "16:9", "count": 1, "seed": 0}
        )


@pytest.mark.asyncio
async def test_ambiguous_ack_retains_only_transport_proven_handles(tmp_path, monkeypatch):
    from gflow_cli.errors import WireFormatError

    output = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_video(self, **kwargs):
            override = active_video_overrides.get()
            override.dispatched = True
            override.known_media_ids[:] = [M]
            override.known_workflow_ids[:] = [W]
            raise WireFormatError(detail="Ambiguous native reply")

    monkeypatch.setattr(worker, "FlowApiClient", Client)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(headless=True))
    monkeypatch.setattr(worker, "_make_provider_dir", lambda _: tmp_path)
    monkeypatch.setattr(worker.json_output, "emit", output.append)
    with pytest.raises(SystemExit) as error:
        await worker.generate_payload(
            "pro1", P, tmp_path, {"prompt": "test", "aspectRatio": "16:9", "count": 1}
        )
    assert error.value.code == 40
    assert output[0]["error"]["media_ids"] == [M]
    assert output[0]["error"]["workflow_ids"] == [W]
    checkpoint = json.loads((tmp_path / "video-checkpoint.json").read_text())
    assert checkpoint["media_ids"] == [M] and checkpoint["workflow_ids"] == [W]
