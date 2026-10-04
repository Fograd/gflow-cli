"""Ambiguous submit replies cannot become a positive native provider rejection."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.native_captcha import native_captcha_provider, take_native_captcha_token_async
from gflow_cli.errors import (
    NativeExtensionUnknownError,
    NativeVideoGenerationUnknownError,
    VoiceMutationUnknownError,
    WafRejectionError,
)
from tests.api.test_native_generation_refusal import M, P, W, refusal
from tests.api.test_native_video_upscale import fixture_models


def reply(rpc, kind):
    first = refusal(rpc)
    if kind == "single":
        return first
    sibling_rpc = "unrelatedRPC" if kind == "foreign-masked" else rpc
    sibling = (
        ["wrb.fr", sibling_rpc, json.dumps([None, None, None, [[M, P, W]]])]
        if kind == "ack"
        else ["wrb.fr", sibling_rpc, None, None, None, [5], "generic"]
    )
    return first + "\n" + json.dumps([sibling])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,rpc",
    [
        ("extension", "fZytfe"),
        ("edit", "jIps6"),
        ("reference", "MZZa6b"),
        ("promotion", "p0UkFb"),
        ("voice", "no0P6"),
    ],
)
@pytest.mark.parametrize("kind", ["single", "masked", "ack", "foreign-masked"])
async def test_real_native_call_ambiguity_is_unknown_without_rejected_telemetry(
    surface, rpc, kind, monkeypatch
):
    from gflow_cli.api import native_extension as extension
    from gflow_cli.api import native_reference_video as reference
    from gflow_cli.api import native_video_edit as edit
    from gflow_cli.api import native_video_upscale as promotion
    from gflow_cli.api.transports import migrated_resources, native_voices

    page = SimpleNamespace(
        url="https://flow.google.com/project/" + P,
        evaluate=AsyncMock(return_value={"status": 200, "text": reply(rpc, kind)}),
    )
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )

    async def mint(minter, action):
        return await take_native_captcha_token_async(page, action)

    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", mint)
    if surface == "voice":
        monkeypatch.setattr(migrated_resources, "read_project_payload", AsyncMock(return_value=[]))

        async def audio_token(_page):
            return await take_native_captcha_token_async(page, "AUDIO_GENERATION")

        monkeypatch.setattr(native_voices, "_mint_audio_token", audio_token)
    else:
        module = {
            "extension": extension,
            "edit": edit,
            "reference": reference,
            "promotion": promotion,
        }[surface]
        if surface == "promotion":
            monkeypatch.setattr(
                module,
                "read_promotion_source",
                AsyncMock(
                    return_value=SimpleNamespace(kind="video", width=160, height=90, workflow_id=W)
                ),
            )
        else:
            monkeypatch.setattr(
                module,
                "read_project_payload",
                AsyncMock(return_value=[None, None, [[M, P, W, None, None, None, []]]]),
            )
            if surface != "reference":
                monkeypatch.setattr(
                    module,
                    "parse_media_snapshot",
                    lambda *_: {
                        "media": [{"media_id": M, "kind": "video", "width": 160, "height": 90}]
                    },
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

        async def metadata(_page, method, *_):
            if method == "nzlxg":
                return [None, None, None, 2]
            if surface == "promotion":
                return fixture_models(15, 2)
            return [[None, None, None, None, [["Native family", [usage], None, "family"]]]]

        monkeypatch.setattr(module, "_read_native", metadata)

    positive = kind in {"single", "foreign-masked"}
    expected = (
        WafRejectionError
        if positive
        else VoiceMutationUnknownError
        if surface == "voice"
        else NativeVideoGenerationUnknownError
        if surface == "reference"
        else promotion.NativeVideoUpscaleUnknownError
        if surface == "promotion"
        else NativeExtensionUnknownError
    )
    phases = []
    with native_captcha_provider(
        AsyncMock(return_value="replacement" * 5),
        project_id=P,
        action="AUDIO_GENERATION" if surface == "voice" else "VIDEO_GENERATION",
        observe=phases.append,
    ):
        with pytest.raises(expected):
            if surface == "extension":
                await extension.extend_native_video(
                    client,
                    project_id=P,
                    media_id=M,
                    prompt="Continue",
                    model_key="actual-native-key",
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
            elif surface == "reference":
                await reference.generate_native_reference_video(
                    client,
                    project_id=P,
                    prompt="Animate",
                    reference_image_ids=(M,),
                    model_key="actual-native-key",
                )
            elif surface == "promotion":
                await promotion.upscale_native_video(client, project_id=P, media_id=M)
            else:
                await native_voices.create_saved_voice(page, P, "Test", "Charon", "Hello", "Calm")
    assert phases == ["submitted", "rejected" if positive else "unknown"]
    page.evaluate.assert_awaited_once()
    if surface != "voice":
        client._checkin_page.assert_called_once_with(page)
