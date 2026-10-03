import json
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.errors import ConfigurationError, NativeMediaMutationUnknownError
from gflow_cli.selfhost import native_worker

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
async def test_worker_rights_refused_before_client(monkeypatch, tmp_path):
    constructor = Mock(side_effect=AssertionError("must not open browser"))
    monkeypatch.setattr(native_worker, "FlowApiClient", constructor)
    with pytest.raises(ConfigurationError):
        await native_worker.execute(
            "upload-video",
            "fixture",
            {"project_id": P, "path": str(tmp_path / "missing.mp4"), "rights_confirmed": False},
        )
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_worker_private_snapshot_lifetime_before_service(monkeypatch, tmp_path):
    source = tmp_path / "one.mp4"
    source.write_bytes(b"\x00\x00\x00\x0cftypisom")
    seen = []

    async def service(profile, project, private):
        assert private != source and private.is_file()
        seen.append(private)
        return {"media_id": M, "project_id": P}

    monkeypatch.setattr(
        "gflow_cli.services.native_media.upload_private_snapshot", AsyncMock(side_effect=service)
    )
    result = await native_worker.execute(
        "upload-video", "fixture", {"project_id": P, "path": str(source), "rights_confirmed": True}
    )
    assert result["media_id"] == M
    assert len(seen) == 1 and not seen[0].exists()
    assert source.exists()


def test_worker_unknown_has_exit40_and_only_safe_recovery(monkeypatch, capsys):
    error = NativeMediaMutationUnknownError(
        operation="upload", phase="response", project_id=P, known_media_ids=(M,)
    )
    monkeypatch.setattr(native_worker, "execute", AsyncMock(side_effect=error))
    monkeypatch.setattr(
        "sys.argv", ["native_worker", "upload-video", "fixture", json.dumps({"project_id": P})]
    )
    with pytest.raises(SystemExit) as caught:
        native_worker.main()
    assert caught.value.code == 40
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["class"] == "NativeMediaMutationUnknownError"
    assert result["error"]["known_media_ids"] == [M]
    assert result["error"]["retryable"] is False
