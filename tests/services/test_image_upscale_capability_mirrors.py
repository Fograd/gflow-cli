"""Direct read mirrors preserve one exact image scope and observation states."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
RESULT = {
    "project_id": P,
    "media_id": M,
    "capabilities": [
        {
            "resolution": "2k",
            "status": "available",
            "available": True,
            "reason": "enabled_menu_item",
        },
        {
            "resolution": "4k",
            "status": "unknown",
            "available": None,
            "reason": "resolution_unobserved",
        },
    ],
    "scope": "fresh owned image detail-menu observation",
}


def context(seen):
    class Client:
        def __init__(self, **kwargs):
            seen.append(("context", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_image_upscale_capabilities(self, **kwargs):
            seen.append(("read", kwargs))
            return RESULT

    return Client


def test_cli_exact_read_and_json(monkeypatch, tmp_path):
    from gflow_cli import cli_image as cli

    seen = []
    monkeypatch.setattr(cli, "_resolve_profile", lambda p: "one")
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(profile_subdir=lambda p: tmp_path / p, headless=False),
    )
    monkeypatch.setattr(cli, "FlowApiClient", context(seen))
    monkeypatch.setattr(cli, "run_with_handlers", lambda action, **kwargs: asyncio.run(action()))
    result = CliRunner().invoke(
        cli.image, ["upscale-capabilities", M, "--project", P, "--profile", "one", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"status": "ok", **RESULT}
    assert seen[-1] == ("read", {"project_id": P, "media_id": M})


@pytest.mark.asyncio
async def test_registered_direct_mcp_exact_read(monkeypatch, tmp_path):
    from gflow_cli.mcp import tools

    seen = []
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "one")
    monkeypatch.setattr(
        tools,
        "get_settings",
        lambda: SimpleNamespace(profile_subdir=lambda p: tmp_path / p, headless=False),
    )
    monkeypatch.setattr(tools, "FlowApiClient", context(seen))

    @asynccontextmanager
    async def lock(profile):
        yield

    monkeypatch.setattr(tools, "_profile_lock", lock)
    result = await tools.gflow_get_image_upscale_capabilities(project=P, media_id=M, profile="one")
    assert result == {"status": "ok", **RESULT}
    assert seen[-1] == ("read", {"project_id": P, "media_id": M})


@pytest.mark.asyncio
async def test_native_worker_uses_same_sdk_read(monkeypatch, tmp_path):
    from gflow_cli.selfhost import native_worker as worker

    seen = []
    monkeypatch.setattr(worker, "FlowApiClient", context(seen))
    monkeypatch.setattr(worker.auth, "profile_dir", lambda p: tmp_path / p)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(flow_host="flow.google"))
    result = await worker.execute(
        "image-upscale-capabilities", "one", {"project_id": P, "media_id": M}
    )
    assert result == {"status": "ok", **RESULT}
    assert seen[-1] == ("read", {"project_id": P, "media_id": M})
