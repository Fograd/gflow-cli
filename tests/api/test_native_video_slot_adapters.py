"""Explicit video slots must reach CLI workers and direct MCP unchanged."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from click.testing import CliRunner

P, M, E = [str(UUID(int=n)) for n in (1, 2, 3)]
SLOTS = {"referenceImage_1": M, "referenceImage_3": E, "referenceAudio_3": "Charon"}
PROMPT = "@referenceImage_3 then @referenceImage_1 and @referenceAudio_3"


def test_reference_cli_forwards_explicit_mixed_slots(monkeypatch):
    from gflow_cli import cli_native_reference_video as module

    monkeypatch.setattr(module, "_resolve_profile", lambda x: x)
    run = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(module, "run_reference_video", run)
    args = ["--project", P, "--prompt", PROMPT, "--json"]
    for key, value in SLOTS.items():
        args.extend(["--reference-slot", key + "=" + value])
    result = CliRunner().invoke(module.reference_native_command, args)
    assert result.exit_code == 0, result.output
    assert run.call_args.args[2]["referenceSlotIds"] == SLOTS
    assert run.call_args.args[2]["referenceImageIds"] == (M, E)
    assert run.call_args.args[2]["referenceAudioIds"] == ("Charon",)


def test_edit_cli_forwards_explicit_mixed_slots(monkeypatch, tmp_path):
    from gflow_cli import cli_native_video_edit as module
    from gflow_cli.api.native_video_edit import NativeVideoEditStarted

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_resolve_profile", lambda x: "pro2")
    monkeypatch.setattr(module, "FlowApiClient", lambda **_: client)
    started = NativeVideoEditStarted(project_id=P, source_media_id=M, media_ids=(), workflow_ids=())
    run = AsyncMock(return_value=started)
    monkeypatch.setattr(module, "edit_native_video", run)
    monkeypatch.setattr(module, "wait_native_video_edit", AsyncMock(return_value=()))
    args = [
        M,
        "--project",
        P,
        "--prompt",
        PROMPT,
        "--model-key",
        "native",
        "--out-dir",
        str(tmp_path),
        "--json",
    ]
    for key, value in SLOTS.items():
        args.extend(["--reference-slot", key + "=" + value])
    result = CliRunner().invoke(module.edit_native_command, args)
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["reference_slot_ids"] == SLOTS
    assert run.call_args.kwargs["image_ids"] == (M, E)


@pytest.mark.parametrize(
    "name", ["gflow_generate_native_reference_video", "gflow_edit_native_video"]
)
def test_direct_mcp_schema_preserves_explicit_slot_map(name):
    from gflow_cli.mcp import tools

    tool = tools.server._tool_manager.get_tool(name)
    args = {"project": P, "prompt": PROMPT, "reference_slot_ids": SLOTS}
    if name == "gflow_edit_native_video":
        args.update(media_id=M, model_key="native")
    parsed = tool.fn_metadata.arg_model.model_validate(args)
    assert parsed.reference_slot_ids == SLOTS


@pytest.mark.parametrize("edit", [False, True])
@pytest.mark.asyncio
async def test_direct_mcp_executes_explicit_slot_forwarding(edit, monkeypatch, tmp_path):
    from gflow_cli.api.native_extension import new_extension_started
    from gflow_cli.api.native_reference_video import new_reference_started
    from gflow_cli.api.native_video_edit import NativeVideoEditStarted
    from gflow_cli.mcp import tools

    started = (
        NativeVideoEditStarted(**vars(new_extension_started(P, M, 1)))
        if edit
        else new_reference_started(P, 1)
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    generate = AsyncMock(return_value=started)
    setattr(client, "edit_native_video" if edit else "generate_native_reference_video", generate)
    setattr(
        client,
        "wait_native_video_edit" if edit else "wait_native_reference_video",
        AsyncMock(return_value=()),
    )
    monkeypatch.setattr(tools, "FlowApiClient", lambda **_: client)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    kwargs = dict(project=P, prompt=PROMPT, reference_slot_ids=SLOTS, out_dir=str(tmp_path))
    call = tools.gflow_edit_native_video if edit else tools.gflow_generate_native_reference_video
    if edit:
        kwargs.update(media_id=M, model_key="native")
    result = await call(**kwargs)
    assert result["status"] == "ok"
    generate.assert_awaited_once()
    assert generate.call_args.kwargs["reference_slot_ids"] == SLOTS
    assert generate.call_args.kwargs["image_ids" if edit else "reference_image_ids"] == (M, E)
    assert generate.call_args.kwargs["audio_ids" if edit else "reference_audio_ids"] == ("Charon",)


@pytest.mark.parametrize(
    "values", [("bad",), ("referenceImage_1=",), ("referenceImage_1=a", "referenceImage_1=b")]
)
def test_malformed_or_duplicate_cli_slot_refuses(values):
    from gflow_cli.api.native_video_prompt import parse_video_slot_options
    from gflow_cli.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        parse_video_slot_options(values)


@pytest.mark.parametrize(
    "slots,images,prompt",
    [
        ({}, (), "text"),
        ({"referenceImage_3": M}, (M,), "text"),
        ({"referenceImage_8": M}, (), "text"),
        ({"referenceImage_3": M}, (), "@referenceImage_1"),
    ],
)
def test_conflicting_invalid_or_missing_slots_refuse(slots, images, prompt):
    from gflow_cli.api.native_video_prompt import video_slot_inputs
    from gflow_cli.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        video_slot_inputs(prompt, images, (), (), slots)


@pytest.mark.parametrize("edit", [False, True])
@pytest.mark.parametrize(
    "flags",
    [
        ["--reference-slot", "bad"],
        ["--reference-slot", "referenceImage_1="],
        ["--image-ref", M, "--reference-slot", "referenceImage_3=" + E],
    ],
)
def test_cli_bad_slots_use_normal_json_error_before_browser(edit, flags, monkeypatch, tmp_path):
    from unittest.mock import Mock

    from gflow_cli import cli_native_reference_video as reference
    from gflow_cli import cli_native_video_edit as editing

    module = editing if edit else reference
    monkeypatch.setattr(module, "_resolve_profile", lambda _: "pro2")
    browser = Mock()
    worker = AsyncMock()
    if edit:
        monkeypatch.setattr(editing, "FlowApiClient", browser)
    else:
        monkeypatch.setattr(reference, "run_reference_video", worker)
    args = ["--project", P, "--prompt", "test", "--json", "--out-dir", str(tmp_path)] + flags
    if edit:
        args = [M, "--model-key", "native"] + args
    command = editing.edit_native_command if edit else reference.reference_native_command
    result = CliRunner().invoke(command, args)
    assert result.exit_code == 11, result.output
    assert '"class": "ConfigurationError"' in result.output
    assert "reference" in result.output.lower()
    browser.assert_not_called()
    worker.assert_not_awaited()
