"""Video-edit entity grounding, fresh weights and native pools."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_video_edit as module
from gflow_cli.errors import ConfigurationError
from tests.api.transports.test_character_details import E, M, P, fixture

SOURCE = "99999999-9999-4999-8999-999999999999"
WORKFLOW = "88888888-8888-4888-8888-888888888888"


def payload():
    value = fixture()
    value[1].append([WORKFLOW, None, None, ["video", None, False, None, SOURCE], P])
    value[2].append([SOURCE, P, WORKFLOW, None, None, None, None, [None, [160, 90]]])
    return value


def setup(monkeypatch, limits=(3, 2, 5)):
    value = payload()
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"status": 200, "text": "ack"}))
    client = SimpleNamespace(
        settings=SimpleNamespace(flow_host="auto"),
        _checkout_page=AsyncMock(return_value=page),
        _checkin_page=Mock(),
    )
    read = AsyncMock(return_value=value)
    monkeypatch.setattr(module, "read_project_payload", read)
    started = module.new_extension_started(P, SOURCE, 1)
    monkeypatch.setattr(module, "new_extension_started", lambda *_: started)
    usage = [None] * 25
    usage[0] = "edit"
    usage[21] = list(limits)
    models = AsyncMock(
        side_effect=[[[None, None, None, None, [["Omni", [usage]]]]], [None, None, None, 1]]
    )
    monkeypatch.setattr(module, "_read_native", models)
    monkeypatch.setattr(module, "parse_extension_models", lambda *_, **__: [{"model_key": "edit"}])
    mint = AsyncMock(return_value="test")
    monkeypatch.setattr(module, "TokenMinter", lambda *_, **__: SimpleNamespace(mint=mint))
    monkeypatch.setattr(module, "rpc_errors", lambda _: [])
    monkeypatch.setattr(
        module,
        "parse_frames",
        lambda _: [
            ("jIps6", [None, None, None, [[started.media_ids[0], P, started.workflow_ids[0]]]])
        ],
    )
    return value, page, client, read, mint, models, started


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed", [False, True])
async def test_owned_character_dispatch_preserves_fields_and_one_snapshot(monkeypatch, mixed):
    value, page, client, read, mint, models, started = setup(monkeypatch)
    kwargs = {"character_ids": (E,), "prompt": "@character_1"}
    if mixed:
        kwargs = {
            "image_ids": (M, E),
            "reference_slot_ids": {"referenceImage_1": M, "referenceImage_3": E},
            "prompt": "@referenceImage_3 then @referenceImage_1",
        }
    checkpoint = AsyncMock()
    result = await module.edit_native_video(
        client,
        project_id=P,
        media_id=SOURCE,
        model_key="edit",
        end_frame=120,
        on_started=checkpoint,
        **kwargs,
    )
    assert result.media_ids == started.media_ids
    read.assert_awaited_once_with(page, P)
    mint.assert_awaited_once_with("VIDEO_GENERATION")
    checkpoint.assert_awaited_once_with(result)
    page.evaluate.assert_awaited_once()
    row = page.evaluate.call_args.args[1]["args"][0][0]
    assert row[10] == [[E]] and row[8] == ([[None, M]] if mixed else [])
    assert row[1][2][0][0] == [None, [None, None, [E, ""]]]
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["image_cap", "character_cap", "archived", "namespace_collision", "duplicate_entity"]
)
async def test_refusals_never_mint_checkpoint_or_submit(monkeypatch, case):
    limits = (
        (3, 2, 1) if case == "image_cap" else (3, 0, 5) if case == "character_cap" else (3, 2, 5)
    )
    value, page, client, read, mint, models, started = setup(monkeypatch, limits)
    kwargs = {"character_ids": (E,), "prompt": "@character_1"}
    if case == "archived":
        value[1][0][3][2] = True
    elif case == "namespace_collision":
        value[2][0][0] = E
        kwargs = {
            "image_ids": (E,),
            "reference_slot_ids": {"referenceImage_1": E},
            "prompt": "@referenceImage_1",
        }
    elif case == "duplicate_entity":
        value[5].append(value[5][0])
    checkpoint = AsyncMock()
    with pytest.raises(ConfigurationError):
        await module.edit_native_video(
            client,
            project_id=P,
            media_id=SOURCE,
            model_key="edit",
            end_frame=120,
            on_started=checkpoint,
            **kwargs,
        )
    mint.assert_not_awaited()
    checkpoint.assert_not_awaited()
    page.evaluate.assert_not_awaited()
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_zero_audio_pool_visual_character_with_preset_follows_source(monkeypatch):
    value, page, client, read, mint, models, started = setup(monkeypatch, (0, 1, 2))
    value[5][0][3][2][1] = [[None, "charon"]]
    await module.edit_native_video(
        client,
        project_id=P,
        media_id=SOURCE,
        model_key="edit",
        end_frame=120,
        character_ids=(E,),
        prompt="@character_1",
    )
    mint.assert_awaited_once()


@pytest.mark.asyncio
async def test_sdk_character_controls_forward(monkeypatch):
    from gflow_cli.api.client import FlowApiClient

    generate = AsyncMock(return_value="started")
    monkeypatch.setattr(module, "edit_native_video", generate)
    client = object.__new__(FlowApiClient)
    await client.edit_native_video(
        project_id=P,
        media_id=SOURCE,
        prompt="@character_1",
        model_key="edit",
        character_ids=(E,),
        reference_slot_ids={"character_1": E},
    )
    assert generate.call_args.kwargs["character_ids"] == (E,)
    assert generate.call_args.kwargs["reference_slot_ids"] == {"character_1": E}


@pytest.mark.asyncio
async def test_private_edit_worker_character_controls_forward(monkeypatch, tmp_path):
    from gflow_cli.selfhost import native_video_edit_worker as worker

    started = module.NativeVideoEditStarted(
        **vars(module.new_extension_started(P, SOURCE, 1)), end_frame=120
    )
    generate = AsyncMock(return_value=started)
    monkeypatch.setattr(worker, "edit_native_video", generate)
    monkeypatch.setattr(worker, "wait_native_video_edit", AsyncMock(return_value=()))
    context = AsyncMock()
    monkeypatch.setattr(worker, "FlowApiClient", lambda **_: context)
    monkeypatch.setattr(
        worker, "get_settings", lambda: SimpleNamespace(profile_subdir=lambda _: tmp_path)
    )
    result = await worker.run_edit(
        "fixture",
        P,
        {
            "referenceVideo_1": SOURCE,
            "prompt": "@character_2",
            "modelKey": "edit",
            "endFrameIndex_1": 120,
            "characterMediaIds": [E],
            "referenceSlotIds": {"character_2": E},
        },
        tmp_path,
    )
    assert result["results"] == []
    assert generate.call_args.kwargs["character_ids"] == (E,)
    assert generate.call_args.kwargs["reference_slot_ids"] == {"character_2": E}


def test_registered_edit_mcp_character_input():
    from gflow_cli.mcp import tools

    tool = tools.server._tool_manager.get_tool("gflow_edit_native_video")
    result = tool.fn_metadata.arg_model.model_validate(
        {
            "project": P,
            "media_id": SOURCE,
            "prompt": "@character_1",
            "model_key": "edit",
            "character_ref": [E],
        }
    )
    assert result.character_ref == [E]


def test_cli_character_controls_forward(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from click.testing import CliRunner

    from gflow_cli import cli_native_video_edit as command

    started = module.NativeVideoEditStarted(
        **vars(module.new_extension_started(P, SOURCE, 1)), end_frame=120
    )
    api = MagicMock()
    api.__aenter__ = AsyncMock(return_value=api)
    api.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "_resolve_profile", lambda _: "fixture")
    monkeypatch.setattr(command, "FlowApiClient", lambda **_: api)
    generate = AsyncMock(return_value=started)
    monkeypatch.setattr(command, "edit_native_video", generate)
    monkeypatch.setattr(command, "wait_native_video_edit", AsyncMock(return_value=()))
    result = CliRunner().invoke(
        command.edit_native_command,
        [
            SOURCE,
            "--project",
            P,
            "--prompt",
            "@character_1",
            "--model-key",
            "edit",
            "--end-frame",
            "120",
            "--character-ref",
            E,
            "--out-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert generate.call_args.kwargs["character_ids"] == (E,)
