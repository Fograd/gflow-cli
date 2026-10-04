"""Generic video explicit controls validate before browser entry."""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from gflow_cli.cli import main

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("leaf", ["t2v", "i2v", "r2v"])
def test_cli_help_mirrors_provider_controls(leaf):
    result = CliRunner().invoke(main, ["video", leaf, "--help"])
    assert result.exit_code == 0
    for name in ("--captcha-order", "--captcha-retry", "--captcha-token-file"):
        assert name in result.output


def test_cli_count_two_rejected_before_browser():
    with patch("gflow_cli.cli_video._make_provider_dir") as browser:
        result = CliRunner().invoke(
            main, ["video", "t2v", "test", "--project", P, "--count", "2", "--captcha-retry", "2"]
        )
    assert result.exit_code == 2
    assert "count one" in result.output
    browser.assert_not_called()


def test_cli_provider_control_reaches_shared_runner_without_secret():
    runner = AsyncMock()
    with (
        patch("gflow_cli.cli_video._run_t2v", runner),
        patch("gflow_cli.cli_video._resolve_profile", return_value="pro1"),
        patch("gflow_cli.cli_video._make_provider_dir"),
    ):
        result = CliRunner().invoke(
            main, ["video", "t2v", "test", "--project", P, "--captcha-order", "CapSolver"]
        )
    assert result.exit_code == 0, result.output
    assert runner.await_args.kwargs["captcha_controls"] == {"captchaOrder": "CapSolver"}
