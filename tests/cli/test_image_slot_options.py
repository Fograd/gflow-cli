from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_image
from gflow_cli.cli import main
from gflow_cli.mcp import tools


@pytest.mark.parametrize(
    "args",
    [
        ["image", "t2i", "@character_1", "--reference-syntax", "slots", "--json"],
        [
            "image",
            "i2i",
            "@reference_2",
            "--ref",
            "11111111-1111-4111-8111-111111111111",
            "--reference-syntax",
            "slots",
            "--json",
        ],
    ],
)
def test_missing_slot_cli_refuses_before_profile(monkeypatch, args):
    resolver = Mock(side_effect=AssertionError("profile must not be resolved"))
    monkeypatch.setattr(cli_image, "_resolve_profile", resolver)
    result = CliRunner().invoke(main, args)
    assert result.exit_code != 0
    assert "not provided" in result.output
    resolver.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_invalid_syntax_refuses_before_profile(monkeypatch):
    resolver = Mock(side_effect=AssertionError("profile must not be resolved"))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolver)
    result = await tools.gflow_generate_image(prompt="plain", reference_syntax="bad")
    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    resolver.assert_not_called()
