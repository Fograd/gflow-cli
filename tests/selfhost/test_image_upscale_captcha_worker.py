from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.selfhost import image_upscale_worker as worker

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.asyncio
async def test_private_upscale_forwards_owned_ids_and_scopes_before_api(tmp_path, monkeypatch):
    path = tmp_path / "request.json"
    path.write_text(
        json.dumps({"resolution": "2k", "mediaGenerationId": M, "captchaOrder": "CapSolver"})
    )
    active = []
    from contextlib import contextmanager

    @contextmanager
    def scope(payload, project, action):
        assert payload["captchaOrder"] == "CapSolver"
        assert project == P and action == "IMAGE_GENERATION"
        active.append(True)
        try:
            yield
        finally:
            active.pop()

    async def submit(**kwargs):
        assert active
        assert kwargs["media_id"] == M and kwargs["project_id"] == P
        assert kwargs["out_path"] == tmp_path / "upscaled.png"

    client = SimpleNamespace(upsample_image=AsyncMock(side_effect=submit))
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(worker, "private_native_captcha", scope)
    monkeypatch.setattr(worker, "FlowApiClient", MagicMock(return_value=context))
    monkeypatch.setattr(worker, "_make_provider_dir", lambda profile: tmp_path)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(headless=True))
    await worker.upscale("pro1", P, path)
    client.upsample_image.assert_awaited_once()
    assert not active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "controls", [{"resolution": "4k"}, {"captchaRetry": 2}, {"captchaRetry": True}]
)
async def test_unmeasured_controls_refuse_before_scope_or_browser(tmp_path, monkeypatch, controls):
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"resolution": "2k", "mediaGenerationId": M, **controls}))
    scope = MagicMock()
    client = MagicMock()
    monkeypatch.setattr(worker, "private_native_captcha", scope)
    monkeypatch.setattr(worker, "FlowApiClient", client)
    with pytest.raises(ValueError):
        await worker.upscale("pro1", P, path)
    scope.assert_not_called()
    client.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_private_request_no_argv_token_and_cleanup(tmp_path, monkeypatch):
    from gflow_cli.selfhost import runtime
    from gflow_cli.selfhost.store import Store
    from tests.selfhost.test_server import settings

    cfg = settings(tmp_path)
    store = Store(tmp_path)
    directory = tmp_path / "captcha-input"
    directory.mkdir()
    secret = directory / ("a" * 64 + ".token")
    token = "private-test-token-" * 3
    secret.write_text(token)
    secret.chmod(0o600)
    store.submit(
        "images/upscale",
        "pro1",
        {
            "project": P,
            "resolution": "2k",
            "mediaGenerationId": M,
            "captchaSecret": str(secret),
        },
        None,
    )
    job = store.claim("pro1")
    seen = []

    async def subprocess(args, timeout):
        assert args[2] == "gflow_cli.selfhost.image_upscale_worker"
        assert token not in " ".join(args)
        path = Path(args[-1])
        seen.append(path)
        assert path.stat().st_mode & 0o777 == 0o600
        assert json.loads(path.read_text())["captchaSecret"] == str(secret)
        (path.parent / "upscaled.png").write_bytes(b"test")
        return 0, b""

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    result = await runtime.execute(cfg, store, job)
    assert result["media"][0]["mediaGenerationId"] == M
    assert all(not path.exists() for path in seen)
    assert not secret.exists()
