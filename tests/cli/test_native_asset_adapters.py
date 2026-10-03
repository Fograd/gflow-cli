import json
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_native_media
from gflow_cli.cli import main
from gflow_cli.mcp import tools

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("download", [False, True])
def test_cli_controls_reach_native_service(monkeypatch, tmp_path, download):
    act = AsyncMock(return_value={"mediaGenerationId": M, "path": "file.mp4", "url": "protected"})
    monkeypatch.setattr("gflow_cli.services.native_assets.read_asset", act)
    monkeypatch.setattr(cli_native_media, "_resolve_profile", lambda value: "one")
    args = [
        "project",
        "download-media" if download else "get-media",
        "--project",
        P,
        "--media-id",
        M,
        "--json",
    ]
    if download:
        args += ["--output-dir", str(tmp_path)]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mediaGenerationId"] == M
    expected = ("one", P, M, tmp_path) if download else ("one", P, M)
    act.assert_awaited_once_with(*expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("download", [False, True])
async def test_mcp_controls_reach_native_service(monkeypatch, tmp_path, download):
    act = AsyncMock(return_value={"mediaGenerationId": M, "path": "file.mp4", "url": "protected"})
    monkeypatch.setattr("gflow_cli.services.native_assets.read_asset", act)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda value: "one")
    if download:
        result = await tools.gflow_download_native_asset(
            project=P, media_id=M, output_dir=str(tmp_path)
        )
    else:
        result = await tools.gflow_get_native_asset(project=P, media_id=M)
    assert result["mediaGenerationId"] == M
    expected = ("one", P, M, tmp_path) if download else ("one", P, M)
    act.assert_awaited_once_with(*expected)


@pytest.mark.parametrize("leaf", ["get-media", "download-media"])
def test_cli_bad_identity_before_profile(monkeypatch, tmp_path, leaf):
    monkeypatch.setattr(
        cli_native_media, "_resolve_profile", lambda value: pytest.fail("profile accessed")
    )
    args = ["project", leaf, "--project", P, "--media-id", "invalid"]
    if leaf == "download-media":
        args += ["--output-dir", str(tmp_path)]
    assert CliRunner().invoke(main, args).exit_code == 2


@pytest.mark.asyncio
async def test_mcp_bad_identity_before_profile(monkeypatch):
    monkeypatch.setattr(
        tools, "_resolve_and_validate_profile", lambda value: pytest.fail("profile accessed")
    )
    result = await tools.gflow_get_native_asset(project=P, media_id="invalid")
    assert result["status"] == "error"
