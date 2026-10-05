"""All deletion adapters share normalization and acknowledged teardown recovery."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from click.testing import CliRunner

from gflow_cli.cli import main
from gflow_cli.errors import NativeMediaMutationUnknownError
from gflow_cli.mcp import tools
from gflow_cli.selfhost import native_worker
from gflow_cli.services import native_media

P = "11111111-1111-4111-8111-111111111111"
M = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_cli_delete_normalizes_before_service(monkeypatch):
    monkeypatch.setattr("gflow_cli.cli_native_media._resolve_profile", lambda _: "fixture")
    service = AsyncMock(return_value={"deleted": [M], "newly_deleted": [M]})
    monkeypatch.setattr(native_media, "delete_media", service)
    result = CliRunner().invoke(
        main,
        [
            "project",
            "delete-media",
            "--project",
            P,
            "--media-id",
            M.upper(),
            "--media-id",
            M,
            "--confirm-delete",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["deleted"] == [M]
    service.assert_awaited_once_with("fixture", P, (M,))


@pytest.mark.parametrize("adapter", ["mcp", "worker"])
async def test_direct_adapters_use_recovery_service_with_canonical_ids(monkeypatch, adapter):
    error = NativeMediaMutationUnknownError(
        operation="delete", phase="response", project_id=P, known_media_ids=(M,)
    )
    service = AsyncMock(side_effect=error)
    monkeypatch.setattr(native_media, "delete_media", service)
    constructor = Mock(side_effect=AssertionError("adapter must delegate teardown recovery"))
    if adapter == "mcp":
        monkeypatch.setattr(tools, "FlowApiClient", constructor)
        monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda _: "fixture")
        result = await tools.gflow_delete_native_media(P, [M.upper(), M], True, "fixture")
        assert result["error"]["known_media_ids"] == [M]
        assert result["error"]["retryable"] is False
    else:
        monkeypatch.setattr(native_worker, "FlowApiClient", constructor)
        with pytest.raises(NativeMediaMutationUnknownError) as caught:
            await native_worker.execute(
                "media-delete-individual",
                "fixture",
                {
                    "project_id": P,
                    "media_ids": [M.upper(), M],
                },
            )
        assert caught.value is error
    service.assert_awaited_once_with("fixture", P, (M,))
    constructor.assert_not_called()


@pytest.mark.parametrize("cancel", [False, True])
async def test_service_teardown_keeps_all_acknowledged_canonical_handles(monkeypatch, cancel):
    failure = asyncio.CancelledError() if cancel else OSError("private teardown")
    submitted = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            raise failure

        async def delete_native_media(self, **kwargs):
            submitted.append(kwargs)
            return {"deleted": [M], "newly_deleted": [M]}

    monkeypatch.setattr(native_media, "FlowApiClient", lambda **kwargs: Client())
    expected = asyncio.CancelledError if cancel else NativeMediaMutationUnknownError
    with pytest.raises(expected) as caught:
        await native_media.delete_media("fixture", P, (M.upper(), M))
    error = vars(caught.value)["gflow_native_media_unknown"] if cancel else caught.value
    assert error.known_media_ids == (M,) and error.pending_media_ids == ()
    assert submitted == [{"project_id": P, "media_ids": (M,), "confirm_delete": True}]


@pytest.mark.parametrize("confirmation", [False, 1, "true"])
async def test_registered_delete_mcp_keeps_strict_confirmation(monkeypatch, confirmation):
    from mcp.server.mcpserver.exceptions import ToolError
    from pydantic import ValidationError

    service = AsyncMock()
    monkeypatch.setattr(native_media, "delete_media", service)
    tool = tools.server._tool_manager._tools["gflow_delete_native_media"]
    try:
        result = await tool.run(
            {"project": P, "media_ids": [M], "confirm_delete": confirmation}, context=None
        )
    except (ToolError, ValidationError):
        pass
    else:
        assert result["status"] == "error"
    service.assert_not_awaited()
