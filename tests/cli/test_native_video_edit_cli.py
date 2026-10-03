"""Native edit registration and pre-network frame input validation."""

from click.testing import CliRunner

from gflow_cli.cli_video import video


def test_edit_command_registered_and_requires_end_frame():
    runner = CliRunner()
    help_result = runner.invoke(video, ["edit-native", "--help"])
    assert help_result.exit_code == 0
    assert "--image-ref" in help_result.output
    result = runner.invoke(
        video,
        [
            "edit-native",
            "source",
            "--project",
            "project",
            "--prompt",
            "edit",
            "--model-key",
            "key",
        ],
    )
    assert result.exit_code == 2
    assert "--end-frame" in result.output
