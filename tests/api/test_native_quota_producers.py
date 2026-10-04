"""Actual native producer coverage: exact selected keys survive typed refusal."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from gflow_cli.errors import NativeQuotaError

P, M, W = [str(UUID(int=n)) for n in (1, 2, 3)]


def refusal(rpc, reason):
    code = 7 if reason == "PUBLIC_ERROR_MODEL_ACCESS_DENIED" else 8
    error = [code, None, [["type.googleapis.com/google.rpc.ErrorInfo", [reason]]]]
    wire = json.dumps([["wrb.fr", rpc, None, None, None, error, "generic"]])
    return ")]}'\n\n" + str(len(wire)) + "\n" + wire


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,rpc", [("extension", "fZytfe"), ("edit", "jIps6"), ("reference", "MZZa6b")]
)
@pytest.mark.parametrize(
    "reason",
    [
        "PUBLIC_ERROR_USER_REQUESTS_THROTTLED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED",
        "PUBLIC_ERROR_MODEL_ACCESS_DENIED",
    ],
)
async def test_selected_native_quota_is_not_wrapped_unknown(surface, rpc, reason, monkeypatch):
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
    outcome = Mock()
    monkeypatch.setattr(module, "native_captcha_outcome", outcome)
    with pytest.raises(NativeQuotaError) as caught:
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

    details = caught.value.to_problem_details()
    assert details["nativeReason"] == reason
    assert details["nativeModelKey"] == "actual-native-key"
    assert (
        details["nativeOperation"]
        == {"reference": "videos/reference", "extension": "videos/extend", "edit": "videos/edit"}[
            surface
        ]
    )
    assert caught.value.retryable is False
    outcome.assert_called_once_with("rejected")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "PUBLIC_ERROR_USER_REQUESTS_THROTTLED",
        "PUBLIC_ERROR_PER_MODEL_DAILY_QUOTA_REACHED",
        "PUBLIC_ERROR_MODEL_ACCESS_DENIED",
    ],
)
async def test_promotion_selected_quota_is_not_wrapped_unknown(monkeypatch, reason):
    import gflow_cli.api.native_video_upscale as module
    from tests.api.test_native_video_upscale import fixture_models

    page = SimpleNamespace(
        evaluate=AsyncMock(return_value={"status": 200, "text": refusal(module.RPC, reason)})
    )
    client = SimpleNamespace(
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
        settings=SimpleNamespace(flow_host="auto"),
    )
    monkeypatch.setattr(
        module,
        "read_promotion_source",
        AsyncMock(return_value=SimpleNamespace(kind="video", width=640, height=360, workflow_id=W)),
    )

    async def metadata(page, rpc, *args):
        return [None, None, None, 2] if rpc == "nzlxg" else fixture_models(15, 2)

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr(
        "gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="private-token")
    )
    outcome = Mock()
    monkeypatch.setattr(module, "native_captcha_outcome", outcome)
    with pytest.raises(NativeQuotaError) as caught:
        await module.upscale_native_video(client, project_id=P, media_id=M)
    details = caught.value.to_problem_details()
    assert details["nativeReason"] == reason
    assert details["nativeModelKey"] == "native-upsample"
    assert details["nativeOperation"] == "videos/promote"
    assert caught.value.retryable is False
    outcome.assert_called_once_with("rejected")
    page.evaluate.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)
