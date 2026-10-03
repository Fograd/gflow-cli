from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from click.testing import CliRunner

from gflow_cli.cli_native_reference_video import reference_native_command
from gflow_cli.errors import NativeVideoGenerationUnknownError

P, M, W = [str(UUID(int=n)) for n in (1, 2, 3)]


def test_registered_cli_fields_and_unknown_exit_40(monkeypatch):
    import gflow_cli.cli_native_reference_video as module

    monkeypatch.setattr(module, "_resolve_profile", lambda x: x)
    mocked = AsyncMock(
        side_effect=NativeVideoGenerationUnknownError(
            project_id=P, media_ids=(M,), workflow_ids=(W,), phase="video_submit"
        )
    )
    monkeypatch.setattr(module, "run_reference_video", mocked)
    result = CliRunner().invoke(
        reference_native_command, ["--project", P, "--prompt", "Test", "--image-ref", M, "--json"]
    )
    assert result.exit_code == 40
    assert "NativeVideoGenerationUnknownError" in result.output
    assert mocked.call_args.args[2]["referenceImageIds"] == (M,)
    assert mocked.call_args.args[2]["referenceAudioIds"] == ()


@pytest.mark.asyncio
async def test_private_worker_bad_duration_never_creates_client(monkeypatch, tmp_path):
    from unittest.mock import Mock

    import gflow_cli.selfhost.reference_video_worker as module
    from gflow_cli.errors import ConfigurationError

    constructor = Mock()
    monkeypatch.setattr(module, "FlowApiClient", constructor)
    with pytest.raises(ConfigurationError):
        await module.run_reference_video(
            "profile", P, {"prompt": "Test", "referenceImageIds": [M], "duration": True}, tmp_path
        )
    constructor.assert_not_called()


def test_cli_character_refs_forward_unchanged(monkeypatch):
    import gflow_cli.cli_native_reference_video as module

    monkeypatch.setattr(module, "_resolve_profile", lambda x: x)
    mocked = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(module, "run_reference_video", mocked)
    result = CliRunner().invoke(
        reference_native_command,
        ["--project", P, "--prompt", "Use @character_1", "--character-ref", M, "--json"],
    )
    assert result.exit_code == 0, result.output
    assert mocked.call_args.args[2]["referenceCharacterIds"] == (M,)
