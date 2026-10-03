"""Native authenticated scripts must run in their page-owned JavaScript world."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import _engine
from gflow_cli.config import BrowserEngine

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
IMAGE = "44444444-4444-4444-8444-444444444444"


def wire(rpc, payload):
    return json.dumps([["wrb.fr", rpc, json.dumps(payload), None, None, None, "generic"]])


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [BrowserEngine.PATCHRIGHT, BrowserEngine.PLAYWRIGHT])
@pytest.mark.parametrize("operation", ["metadata", "models", "voice-rpc", "voice-mint"])
async def test_native_window_owned_reads_use_engine_compatible_context(
    monkeypatch, engine, operation
):
    monkeypatch.setattr(_engine, "active_engine", lambda: engine)
    expected = {"isolated_context": False} if engine == BrowserEngine.PATCHRIGHT else {}

    async def evaluate(expression, args=None, **kwargs):
        assert "WIZ_global_data" in expression or "window.grecaptcha" in expression
        assert kwargs == expected
        if operation == "voice-mint":
            return "synthetic-native-audio-token"
        rpc = args["rpc"]
        return {"status": 200, "text": wire(rpc, [])}

    page = SimpleNamespace(
        evaluate=AsyncMock(side_effect=evaluate), url="https://flow.google.com/project/" + P
    )
    if operation == "metadata":
        from gflow_cli.api.transports.migrated_rpc import native_rpc

        assert await native_rpc(page, "as29s", [M], "/project/" + P, require_single=True) == []
    elif operation == "models":
        from gflow_cli.api.native_extension import _read_native

        assert await _read_native(page, "HTrJv", [], P) == []
    elif operation == "voice-rpc":
        from gflow_cli.api.transports.native_voices import _rpc

        assert await _rpc(page, P, "as29s", [M]) == []
    else:
        from gflow_cli.api.transports.native_voices import _mint_audio_token

        assert await _mint_audio_token(page) == "synthetic-native-audio-token"
    page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [BrowserEngine.PATCHRIGHT, BrowserEngine.PLAYWRIGHT])
@pytest.mark.parametrize("operation", ["extension", "reference"])
async def test_native_poll_uses_page_owned_context(monkeypatch, engine, operation):
    from gflow_cli.api import native_extension, native_reference_video

    module = native_extension if operation == "extension" else native_reference_video

    monkeypatch.setattr(_engine, "active_engine", lambda: engine)
    expected = {"isolated_context": False} if engine == BrowserEngine.PATCHRIGHT else {}
    started = (
        native_extension.NativeExtensionStarted(P, IMAGE, (M,), (W,))
        if operation == "extension"
        else native_reference_video.NativeReferenceVideoStarted(P, (M,), (W,))
    )
    record = [
        M,
        P,
        W,
        "CAE",
        None,
        [None] * 8 + [[3]],
        None,
        [[None] * 8 + ["https://flow-content.google/video/synthetic"]],
    ]
    page = SimpleNamespace(
        evaluate=AsyncMock(return_value={"status": 200, "text": wire("as29s", record)})
    )
    client = SimpleNamespace(_checkout_page=AsyncMock(return_value=page), _checkin_page=Mock())
    wait = (
        module.wait_native_extension
        if operation == "extension"
        else module.wait_native_reference_video
    )
    results = await wait(client, started, timeout_s=1)
    assert results[0].media_id == M
    assert page.evaluate.call_args.kwargs == expected
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [BrowserEngine.PATCHRIGHT, BrowserEngine.PLAYWRIGHT])
@pytest.mark.parametrize("operation", ["extension", "reference", "edit", "promotion"])
async def test_native_single_submit_uses_page_owned_context(monkeypatch, engine, operation):
    from gflow_cli.api import (
        native_extension,
        native_reference_video,
        native_video_edit,
        native_video_upscale,
    )

    modules = {
        "extension": native_extension,
        "reference": native_reference_video,
        "edit": native_video_edit,
        "promotion": native_video_upscale,
    }
    module = modules[operation]
    monkeypatch.setattr(_engine, "active_engine", lambda: engine)
    expected = {"isolated_context": False} if engine == BrowserEngine.PATCHRIGHT else {}
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    payload = [
        None,
        [[W, None, None, ["Video", None, False, None, M], P]],
        [[M, P, W, None, None, None, None, [None, [160, 90]]]],
        None,
        None,
        [],
    ]
    if operation == "reference":
        payload[2].append([IMAGE, P, W, None, None, None, []])
    models = [[None, None, None, None, [["Omni Flash", [["native"] + [None] * 20 + [[0, 0, 7]]]]]]]
    monkeypatch.setattr(
        module, "_read_native", AsyncMock(side_effect=[models, [None, None, None, 2]])
    )
    if operation != "promotion":
        monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=payload))
        monkeypatch.setattr(
            module,
            "parse_extension_models",
            lambda *args, **kwargs: [
                {
                    "model_key": "native",
                    "aspect_enums": [2],
                    "credits": 4,
                    "duration": 8,
                    "display_name": "Omni Flash",
                }
            ],
        )
    else:
        monkeypatch.setattr(
            module,
            "read_promotion_source",
            AsyncMock(
                return_value=SimpleNamespace(kind="video", width=160, height=90, workflow_id=W)
            ),
        )
        monkeypatch.setattr(
            module,
            "parse_promotion_models",
            lambda *args, **kwargs: [{"model_key": "native", "aspect_enums": [2], "credits": 4}],
        )
    monkeypatch.setattr(
        "gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="synthetic-token")
    )
    if operation == "extension":
        started = native_extension.new_extension_started(P, M, 1)
        monkeypatch.setattr(module, "new_extension_started", lambda *args: started)
    elif operation == "reference":
        started = native_reference_video.new_reference_started(P, 1)
        monkeypatch.setattr(module, "new_reference_started", lambda *args: started)
    elif operation == "edit":
        started = native_extension.new_extension_started(P, M, 1)
        monkeypatch.setattr(module, "new_extension_started", lambda *args: started)
    else:
        started = native_video_upscale.new_promotion_started(P, M, W)
        monkeypatch.setattr(module, "new_promotion_started", lambda *args: started)
    rpc = "MZZa6b" if operation == "reference" else "jIps6" if operation == "edit" else module.RPC
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda text: [
            (rpc, [None, None, None, [[started.media_ids[0], P, started.workflow_ids[0]]]])
        ],
    )
    if operation == "extension":
        await module.extend_native_video(
            client, project_id=P, media_id=M, prompt="Continue", model_key="native"
        )
    elif operation == "reference":
        await module.generate_native_reference_video(
            client,
            project_id=P,
            prompt="Use image",
            reference_image_ids=(IMAGE,),
            model_key="native",
        )
    elif operation == "edit":
        await module.edit_native_video(
            client, project_id=P, media_id=M, prompt="Edit", model_key="native", end_frame=24
        )
    else:
        await module.upscale_native_video(client, project_id=P, media_id=M)
    page.evaluate.assert_awaited_once()
    assert page.evaluate.call_args.kwargs == expected
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [BrowserEngine.PATCHRIGHT, BrowserEngine.PLAYWRIGHT])
async def test_native_archive_uses_page_owned_context_once(monkeypatch, engine):
    from gflow_cli.api.transports import migrated_resources as module

    monkeypatch.setattr(_engine, "active_engine", lambda: engine)
    expected = {"isolated_context": False} if engine == BrowserEngine.PATCHRIGHT else {}
    monkeypatch.setattr(
        module,
        "read_project",
        AsyncMock(
            return_value=[
                {
                    "media_id": M,
                    "project_id": P,
                    "workflow_id": W,
                    "archived": False,
                    "batch_media_ids": [M],
                }
            ]
        ),
    )
    reply = [[W, None, None, [None, None, True], P]]
    page = SimpleNamespace(
        evaluate=AsyncMock(
            return_value={
                "status": 200,
                "text": wire("pGCYOe", [reply]),
            }
        )
    )
    assert await module.trash_media(page, P, [M]) == [M]
    page.evaluate.assert_awaited_once()
    assert page.evaluate.call_args.kwargs == expected
