"""Native preset audio normalization and fresh availability, not rendered acceptance."""

import pytest

from gflow_cli.api.native_extension import new_extension_started
from gflow_cli.api.native_reference_video import new_reference_started, reference_args
from gflow_cli.api.native_video_audio import (
    audio_wire_id,
    normalize_audio_reference,
    validate_audio_presets,
)
from gflow_cli.api.native_video_edit import video_edit_args
from gflow_cli.api.reference_markers import ReferenceSlot
from gflow_cli.errors import ConfigurationError

P = "11111111-1111-4111-8111-111111111111"
V = "22222222-2222-4222-8222-222222222222"


def catalog(*names):
    rows = []
    for name in names:
        details = [None] * 11
        details[10] = [
            [
                None,
                "description",
                None,
                "https://gstatic.com/aitestkitchen/voices/samples/" + name + ".wav",
            ]
        ]
        rows.append([None, 3, name, details])
    return [None, [], [], rows]


@pytest.mark.parametrize("value", ["Charon", "charon", "CHARON", "voices/charon"])
def test_measured_forms_normalize(value):
    assert normalize_audio_reference(value) == "Charon"
    assert audio_wire_id(value) == "charon"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/charon",
        "foo/charon",
        "voices/Charon",
        "voices/charon/",
        "voices/unknown",
        "voices/",
        "unknown",
        "",
        None,
        42,
    ],
)
def test_unmeasured_forms_refuse(value):
    with pytest.raises(ConfigurationError):
        normalize_audio_reference(value)


def test_uuid_preserved_and_not_treated_as_preset():
    assert normalize_audio_reference(V) == V
    assert audio_wire_id(V) == V
    assert validate_audio_presets(None, (V,)) == (V,)


def test_fresh_unique_preset_and_uuid_separate():
    assert validate_audio_presets(catalog("charon"), ("voices/charon", V)) == (V,)


@pytest.mark.parametrize(
    "payload,refs",
    [
        (catalog(), ("Charon",)),
        (catalog("charon", "charon"), ("Charon",)),
        (None, ("Charon",)),
        (catalog("charon"), ("Charon", "voices/charon")),
    ],
)
def test_missing_ambiguous_or_duplicate_refuses(payload, refs):
    with pytest.raises(ConfigurationError):
        validate_audio_presets(payload, refs)


@pytest.mark.parametrize("kind", ["edit", "reference"])
def test_native_vector_and_inline_audio_use_bare_resource(kind):
    slots = {"referenceAudio_3": ReferenceSlot("audio", "voices/charon")}
    if kind == "edit":
        args = video_edit_args(
            new_extension_started(P, V, 1),
            prompt="Speak @referenceAudio_3",
            model_key="native",
            aspect="16:9",
            token="t",
            start_frame=0,
            end_frame=24,
            audio_ids=("voices/charon",),
            reference_slots=slots,
        )
        vector = args[0][0][9]
    else:
        args = reference_args(
            new_reference_started(P, 1),
            prompt="Speak @referenceAudio_3",
            image_ids=(),
            audio_ids=("voices/charon",),
            reference_slots=slots,
            model_key="native",
            aspect="16:9",
            resolution="720p",
            token="t",
        )
        vector = args[0][0][7]
    assert vector == [["charon"]]
    prompt = args[0][0][1 if kind == "edit" else 0]
    assert prompt[2][0][1] == [None, [None, ["charon", ""]]]


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed", [False, True])
async def test_edit_available_preset_reaches_single_dispatch(monkeypatch, mixed):
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_video_edit as module
    from tests.api.test_native_video_edit_characters import SOURCE, setup

    value, page, client, read, mint, models, started = setup(monkeypatch)
    value[3] = catalog("charon")[3]
    kwargs = {"audio_ids": ("voices/charon",), "prompt": "@referenceAudio_1"}
    if mixed:
        kwargs = {
            "audio_ids": ("voices/charon",),
            "prompt": "@referenceAudio_3",
            "reference_slot_ids": {"referenceAudio_3": "voices/charon"},
        }
    checkpoint = AsyncMock()
    await module.edit_native_video(
        client,
        project_id=P,
        media_id=SOURCE,
        model_key="edit",
        end_frame=24,
        on_started=checkpoint,
        **kwargs,
    )
    read.assert_awaited_once()
    mint.assert_awaited_once_with("VIDEO_GENERATION")
    checkpoint.assert_awaited_once()
    page.evaluate.assert_awaited_once()
    row = page.evaluate.call_args.args[1]["args"][0][0]
    assert row[9] == [["charon"]] and row[1][2][0][0] == [None, [None, ["charon", ""]]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["missing", "duplicate", "zero_cap", "unknown_cap", "duplicate_inputs"]
)
async def test_preset_preflight_refuses_before_mint_or_dispatch(monkeypatch, case):
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_video_edit as module
    from tests.api.test_native_video_edit_characters import SOURCE, setup

    limits = (
        (0, 2, 5) if case == "zero_cap" else (None, 2, 5) if case == "unknown_cap" else (3, 2, 5)
    )
    value, page, client, read, mint, models, started = setup(monkeypatch, limits)
    value[3] = catalog(
        *([] if case == "missing" else ["charon", "charon"] if case == "duplicate" else ["charon"])
    )[3]
    checkpoint = AsyncMock()
    refs = ("Charon", "voices/charon") if case == "duplicate_inputs" else ("Charon",)
    with pytest.raises(ConfigurationError):
        await module.edit_native_video(
            client,
            project_id=P,
            media_id=SOURCE,
            model_key="edit",
            prompt="@referenceAudio_1",
            audio_ids=refs,
            end_frame=24,
            on_started=checkpoint,
        )
    mint.assert_not_awaited()
    checkpoint.assert_not_awaited()
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", [False, True])
async def test_private_workers_preserve_preset_and_position(monkeypatch, tmp_path, edit):
    from unittest.mock import AsyncMock, MagicMock

    from gflow_cli.api.native_video_edit import NativeVideoEditStarted
    from gflow_cli.selfhost import native_video_edit_worker as ew
    from gflow_cli.selfhost import reference_video_worker as rw

    worker = ew if edit else rw
    api = MagicMock()
    api.__aenter__ = AsyncMock(return_value=api)
    api.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, "FlowApiClient", lambda **_: api)
    started = (
        NativeVideoEditStarted(**vars(worker.new_extension_started(P, V, 1)), end_frame=24)
        if edit
        else worker.new_reference_started(P, 1)
    )
    generate = AsyncMock(return_value=started)
    monkeypatch.setattr(
        worker, "edit_native_video" if edit else "generate_native_reference_video", generate
    )
    monkeypatch.setattr(
        worker,
        "wait_native_video_edit" if edit else "wait_native_reference_video",
        AsyncMock(return_value=()),
    )
    body = {
        "prompt": "Use @referenceAudio_3",
        "modelKey": "edit" if edit else "reference",
        "referenceSlotIds": {"referenceAudio_3": "voices/charon"},
    }
    body.update(
        {"referenceVideo_1": V, "audioMediaIds": ["voices/charon"], "endFrameIndex_1": 24}
        if edit
        else {"referenceAudioIds": ["voices/charon"]}
    )
    await (worker.run_edit if edit else worker.run_reference_video)("fixture", P, body, tmp_path)
    assert generate.call_args.kwargs["audio_ids" if edit else "reference_audio_ids"] == (
        "voices/charon",
    )
    assert generate.call_args.kwargs["reference_slot_ids"] == {"referenceAudio_3": "voices/charon"}


def test_native_catalog_capitalization_is_presentation_only():
    assert validate_audio_presets(catalog("Charon"), ("voices/charon",)) == ()
    with pytest.raises(ConfigurationError):
        validate_audio_presets(catalog("Charon", "charon"), ("Charon",))
