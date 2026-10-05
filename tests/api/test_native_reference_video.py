from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from gflow_cli.api.native_reference_video import (
    generate_native_reference_video,
    new_reference_started,
    reference_args,
    validate_reference_assets,
)
from gflow_cli.errors import ConfigurationError, NativeVideoGenerationUnknownError

P, IMAGE, A, W = [str(UUID(int=n)) for n in range(1, 5)]


def test_exact_reference_request_audio_resolution_and_positional_tokens():
    started = new_reference_started(P, 2)
    args = reference_args(
        started,
        prompt="Use @referenceImage_1 then @referenceAudio_1 and @literal",
        image_ids=(IMAGE,),
        audio_ids=(A,),
        model_key="actual-native-key",
        aspect="16:9",
        resolution="1080p",
        token="private",
    )
    row = args[0][0]
    assert row[1] == [[None, IMAGE]]
    assert row[7] == [[A]]
    assert row[11] == [2]
    assert row[3] == 2
    assert row[0][2][0] == [
        ["Use "],
        [None, [[IMAGE, ""]]],
        [" then "],
        [None, [None, [A, ""]]],
        [" and @literal"],
    ]
    assert row[5][4:] == [started.media_seeds[0], started.workflow_seeds[0]]
    assert len(args[0]) == 2
    assert args[1][5] == P


def test_ownership_and_exclusive_audio_arm():
    image = [IMAGE, P, W, None, None, None, []]
    audio = [
        A,
        P,
        str(UUID(int=6)),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [[None, "performance"]],
    ]
    validate_reference_assets(
        [None, [[audio[2], None, None, ["audio", None, None, None, A], P]], [image, audio]],
        P,
        (IMAGE,),
        (A,),
    )
    audio[6] = []
    with pytest.raises(ConfigurationError):
        validate_reference_assets(
            [None, [[audio[2], None, None, ["audio", None, None, None, A], P]], [image, audio]],
            P,
            (IMAGE,),
            (A,),
        )


@pytest.mark.asyncio
async def test_malformed_reference_budget_never_opens_browser():
    client = AsyncMock()
    with pytest.raises(ConfigurationError):
        await generate_native_reference_video(
            client, project_id=P, prompt="x", reference_image_ids=(IMAGE,) * 8, model_key="native"
        )
    client._checkout_page.assert_not_awaited()


def test_generic_unknown_has_no_phantom_source_and_canonical_exit():
    from gflow_cli.errors import EXIT_CODE_MAP

    error = NativeVideoGenerationUnknownError(
        project_id=P, media_ids=(IMAGE,), workflow_ids=(W,), phase="video_submit"
    )
    out = error.to_problem_details()
    assert out["media_ids"] == [IMAGE] and out["outcome_unknown"] is True
    assert "source_media_id" not in out and error.retryable is False
    assert EXIT_CODE_MAP[type(error)] == 40


def test_audio_only_dto_and_missing_reserved_marker():
    args = reference_args(
        new_reference_started(P, 1),
        prompt="Sound @referenceAudio_1",
        image_ids=(),
        audio_ids=(A,),
        model_key="native",
        aspect="1:1",
        resolution="720p",
        token="token",
    )
    assert args[0][0][1] == [] and args[0][0][7] == [[A]]
    assert len(args[0][0]) == 8  # 720p default, no invented duration/seed field
    with pytest.raises(ConfigurationError):
        reference_args(
            new_reference_started(P, 1),
            prompt="@referenceImage_2",
            image_ids=(IMAGE,),
            model_key="native",
            aspect="16:9",
            resolution="720p",
            token="token",
        )


@pytest.mark.asyncio
async def test_fresh_audio_caps_single_dispatch_checkpoint_and_unknown(monkeypatch):
    from unittest.mock import Mock

    import gflow_cli.api.native_reference_video as module

    page = AsyncMock()
    client = AsyncMock()
    client._checkout_page.return_value = page
    client._checkin_page = Mock()
    image = [IMAGE, P, W, None, None, None, []]
    audio = [
        A,
        P,
        str(UUID(int=6)),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [[None, "performance"]],
    ]
    monkeypatch.setattr(
        module,
        "read_project_payload",
        AsyncMock(
            return_value=[
                None,
                [[audio[2], None, None, ["audio", None, None, None, A], P]],
                [image, audio],
            ]
        ),
    )
    usage = [None] * 25
    usage[0] = "actual-key"
    usage[4] = [[2, [[None, 10]]]]
    usage[7] = [[[[1, 6, 18, 19]]]]
    usage[12] = [[2]]
    usage[16] = 8
    usage[21] = [5, None, 7]
    usage[23] = [[1, 2]]

    async def metadata(_page, rpc, *_):
        return (
            [None, None, None, 2]
            if rpc == "nzlxg"
            else [[None, None, None, None, [["Omni Flash", [usage], None, "actual-family"]]]]
        )

    monkeypatch.setattr(module, "_read_native", metadata)
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", AsyncMock(return_value="token"))
    order = []

    async def checkpoint(started):
        order.append(("checkpoint", started))

    async def failure(*_):
        order.append(("dispatch", None))
        raise TimeoutError("private body must never surface")

    page.evaluate.side_effect = failure
    with pytest.raises(NativeVideoGenerationUnknownError) as caught:
        await generate_native_reference_video(
            client,
            project_id=P,
            prompt="@referenceAudio_1",
            reference_image_ids=(IMAGE,),
            reference_audio_ids=(A,),
            count=2,
            on_started=checkpoint,
        )
    assert [kind for kind, _ in order] == ["checkpoint", "dispatch"]
    assert len(caught.value.media_ids) == 2
    assert "private body" not in str(caught.value)
    page.evaluate.assert_awaited_once()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_poll_unrelated_response_preserves_exact_ids_without_source(monkeypatch):
    from unittest.mock import Mock

    import gflow_cli.api.native_reference_video as module

    started = new_reference_started(P, 1)
    page = AsyncMock()
    client = AsyncMock()
    client._checkout_page.return_value = page
    client._checkin_page = Mock()
    page.evaluate.return_value = {"status": 200, "text": "not inspected"}
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda *_: [("as29s", [IMAGE, P, W, None, None, None, None, []])],
    )
    monkeypatch.setattr(module, "rpc_errors", lambda *_: [])
    with pytest.raises(NativeVideoGenerationUnknownError) as caught:
        await module.wait_native_reference_video(client, started, timeout_s=1)
    assert caught.value.media_ids == started.media_ids
    assert caught.value.phase == "video_poll"
    client._checkin_page.assert_called_once_with(page)
