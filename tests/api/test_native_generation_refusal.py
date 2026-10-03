"""Positive refusal reasons are typed; bare status never invents a rejection."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from gflow_cli.errors import (
    NativeExtensionUnknownError,
    NativeVideoGenerationUnknownError,
    VoiceMutationUnknownError,
    WafRejectionError,
)

P, M, W = [str(UUID(int=n)) for n in (1, 2, 3)]


def refusal(rpc, reason=True):
    error = (
        [7, None, [["type.googleapis.com/google.rpc.ErrorInfo", ["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]]]
        if reason
        else [7]
    )
    wire = json.dumps([["wrb.fr", rpc, None, None, None, error, "generic"]])
    return ")]}'\n\n" + str(len(wire)) + "\n" + wire


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,rpc", [("extension", "fZytfe"), ("edit", "jIps6"), ("reference", "MZZa6b")]
)
@pytest.mark.parametrize("reason", [True, False])
async def test_actual_native_submit_refusal_not_swallowed(surface, rpc, reason, monkeypatch):
    from gflow_cli.api import native_extension as extension
    from gflow_cli.api import native_reference_video as reference
    from gflow_cli.api import native_video_edit as edit

    module = {"extension": extension, "edit": edit, "reference": reference}[surface]
    page = SimpleNamespace(
        evaluate=AsyncMock(return_value={"status": 200, "text": refusal(rpc, reason)})
    )
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    image = [M, P, W, None, None, None, []]
    monkeypatch.setattr(
        module, "read_project_payload", AsyncMock(return_value=[None, None, [image]])
    )
    if surface != "reference":
        monkeypatch.setattr(
            module,
            "parse_media_snapshot",
            lambda *_: {"media": [{"media_id": M, "kind": "video", "width": 160, "height": 90}]},
        )
    if surface == "edit":
        monkeypatch.setattr(
            module, "project_media", lambda *_: [{"media_id": M, "archived": False}]
        )
    usage = [None] * 25
    usage[0] = "actual-native-key"
    usage[4] = [[2, [[None, 10]]]]
    usage[7] = [[[[1, 6, 14, 20]]]]
    usage[12] = [[2]]
    usage[21] = [5, None, 7]

    async def metadata(_page, rpc, *_):
        return (
            [None, None, None, 2]
            if rpc == "nzlxg"
            else [[None, None, None, None, [["Native family", [usage], None, "native-family"]]]]
        )

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr(
        "gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="private-token")
    )
    expected = (
        WafRejectionError
        if reason
        else NativeVideoGenerationUnknownError
        if surface == "reference"
        else NativeExtensionUnknownError
    )
    with pytest.raises(expected):
        if surface == "extension":
            await extension.extend_native_video(
                client, project_id=P, media_id=M, prompt="Continue", model_key="actual-native-key"
            )
        elif surface == "edit":
            await edit.edit_native_video(
                client,
                project_id=P,
                media_id=M,
                prompt="Edit",
                model_key="actual-native-key",
                end_frame=24,
            )
        else:
            await reference.generate_native_reference_video(
                client,
                project_id=P,
                prompt="Animate",
                reference_image_ids=(M,),
                model_key="actual-native-key",
            )
    page.evaluate.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [True, False])
async def test_tts_positive_preview_refusal_propagates_without_ack(reason, monkeypatch):
    import gflow_cli.api.transports.migrated_resources as resources
    from gflow_cli.api.transports import native_voices as module

    monkeypatch.setattr(resources, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "_mint_audio_token", AsyncMock(return_value="private-token"))
    page = SimpleNamespace(
        evaluate=AsyncMock(return_value={"status": 200, "text": refusal("no0P6", reason)})
    )
    with pytest.raises(WafRejectionError if reason else VoiceMutationUnknownError):
        await module.create_saved_voice(page, P, "Test", "Charon", "Hello", "Calm")
    page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_tts_refusal_after_preview_ack_keeps_known_handles(monkeypatch):
    import gflow_cli.api.transports.migrated_resources as resources
    from gflow_cli.api.transports import native_voices as module

    monkeypatch.setattr(resources, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "_mint_audio_token", AsyncMock(return_value="private-token"))
    rpc = AsyncMock(side_effect=[[[[M, P, W]], []], WafRejectionError()])
    monkeypatch.setattr(module, "_rpc", rpc)
    with pytest.raises(VoiceMutationUnknownError) as caught:
        await module.create_saved_voice(None, P, "Test", "Charon", "Hello", "Calm")
    assert caught.value.to_problem_details()["known_media_ids"] == [M]
    assert caught.value.to_problem_details()["phase"] == "save"
    assert rpc.await_count == 2
