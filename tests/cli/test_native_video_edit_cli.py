"""Native edit registration and optional-end propagation."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_native_video_edit as module
from gflow_cli.api.native_video_edit import NativeVideoEditStarted
from gflow_cli.cli_video import video

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("end", [None, 120])
def test_edit_command_propagates_optional_or_explicit_end(end, monkeypatch, tmp_path):
    runner = CliRunner()
    help_result = runner.invoke(video, ["edit-native", "--help"])
    assert help_result.exit_code == 0
    assert "--image-ref" in help_result.output
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_resolve_profile", lambda _: "pro1")
    monkeypatch.setattr(module, "FlowApiClient", lambda **_: client)
    started = NativeVideoEditStarted(
        project_id=P,
        source_media_id=M,
        media_ids=(),
        workflow_ids=(),
        end_frame=end or 24,
        source_duration_seconds=1 if end is None else None,
    )
    edit = AsyncMock(return_value=started)
    monkeypatch.setattr(module, "edit_native_video", edit)
    monkeypatch.setattr(module, "wait_native_video_edit", AsyncMock(return_value=()))
    args = [
        "edit-native",
        M,
        "--project",
        P,
        "--prompt",
        "edit",
        "--model-key",
        "key",
        "--out-dir",
        str(tmp_path),
        "--json",
    ]
    if end is not None:
        args += ["--end-frame", str(end)]
    result = runner.invoke(video, args)
    assert result.exit_code == 0, result.output
    assert edit.await_args.kwargs["end_frame"] == end
    assert '"endFrameIndex":' in result.output
