from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from gflow_cli.cli import main
from gflow_cli.mcp import tools

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def test_upload_cli_requires_rights_before_profile(monkeypatch):
    resolve = Mock(side_effect=AssertionError("must not resolve profile"))
    monkeypatch.setattr("gflow_cli.cli_native_media._resolve_profile", resolve)
    result = CliRunner().invoke(main, ["project", "upload-video", "missing.mp4", "--project", P])
    assert result.exit_code != 0 and "rights" in result.output.lower()
    resolve.assert_not_called()


def test_archive_cli_requires_confirmation_before_profile(monkeypatch):
    resolve = Mock(side_effect=AssertionError("must not resolve profile"))
    monkeypatch.setattr("gflow_cli.cli_native_media._resolve_profile", resolve)
    result = CliRunner().invoke(main, ["project", "archive", "--project", P, "--media-id", M])
    assert result.exit_code != 0 and "confirmation" in result.output.lower()
    resolve.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("rights", [False, 1, "true"])
async def test_mcp_upload_refuses_rights_before_profile(monkeypatch, rights):
    resolve = Mock(side_effect=AssertionError("must not resolve profile"))
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolve)
    result = await tools.gflow_upload_video("missing.mp4", P, rights_confirmed=rights)
    assert result["status"] == "error"
    resolve.assert_not_called()


def test_cli_upload_snapshot_exists_during_client_service_and_is_removed(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli import cli_native_media

    source = tmp_path / "source.mp4"
    source.write_bytes(b"\x00\x00\x00\x0cftypisom")
    observed = []

    async def service(profile, project, private):
        assert private != source and private.read_bytes() == source.read_bytes()
        assert private.stat().st_mode & 0o777 == 0o600
        observed.append(private)
        return {"media_id": M, "project_id": P, "scope": "native-project-video-upload"}

    monkeypatch.setattr(cli_native_media, "_resolve_profile", lambda _: "fixture")
    monkeypatch.setattr(cli_native_media, "upload_private_snapshot", AsyncMock(side_effect=service))
    result = CliRunner().invoke(
        main,
        ["project", "upload-video", str(source), "--project", P, "--rights-confirmed", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert len(observed) == 1 and not observed[0].exists()
    assert source.exists() and str(source) not in result.output


@pytest.mark.asyncio
async def test_mcp_unknown_media_mutation_preserves_structured_handles(monkeypatch):
    from unittest.mock import AsyncMock

    from gflow_cli.errors import NativeMediaMutationUnknownError

    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
    monkeypatch.setattr(
        "gflow_cli.services.native_media.archive_media",
        AsyncMock(
            side_effect=NativeMediaMutationUnknownError(
                operation="archive", phase="response", project_id=P, known_media_ids=(M,)
            )
        ),
    )
    result = await tools.gflow_archive_media([M], P, confirm_archive=True)
    assert result["error"]["known_media_ids"] == [M]
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,flag,args",
    [
        ("gflow_upload_video", "rights_confirmed", {"path": "missing.mp4", "project": P}),
        ("gflow_archive_media", "confirm_archive", {"media_ids": [M], "project": P}),
    ],
)
@pytest.mark.parametrize("value", [False, 1, "true"])
async def test_registered_mcp_consent_is_not_coerced(monkeypatch, tool_name, flag, args, value):
    from unittest.mock import AsyncMock

    from mcp.server.mcpserver.exceptions import ToolError
    from pydantic import ValidationError

    resolve = Mock(return_value="fixture")
    service = AsyncMock(return_value={"archived_media_ids": [M], "media_id": M})
    monkeypatch.setattr("gflow_cli.services.native_media.archive_media", service)
    monkeypatch.setattr("gflow_cli.services.native_media.upload_private_snapshot", service)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", resolve)
    tool = tools.server._tool_manager._tools[tool_name]
    try:
        result = await tool.run({**args, flag: value}, context=None)
    except (ToolError, ValidationError):
        pass
    else:
        assert result["status"] == "error"
    resolve.assert_not_called()
    service.assert_not_awaited()
