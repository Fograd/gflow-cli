"""Shared SDK, CLI, direct MCP, and worker account resource mirrors."""

import asyncio
import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from gflow_cli.api.client import FlowApiClient
from tests.services.test_account_resources import Client


@pytest.mark.asyncio
async def test_sdk_derives_private_profile_principal_and_rechecks_marker(tmp_path):
    profile = tmp_path / "profiles" / "one"
    profile.mkdir(parents=True)
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    client = Client()
    client.profile_dir = profile
    client.settings = SimpleNamespace(
        home=tmp_path, profile_subdir=lambda name: tmp_path / "profiles" / name
    )
    result = await FlowApiClient.list_account_resources(
        client, kind="character", max_projects=1, max_pages=1, max_seconds=7
    )
    assert result["resources"][0]["kind"] == "character"
    assert (tmp_path / "native_inventory" / "account_resources.sqlite3").exists()


@pytest.mark.parametrize("phase", ["discovery", "catalog"])
@pytest.mark.asyncio
async def test_sdk_rejects_marker_change_after_read(tmp_path, phase):
    profile = tmp_path / "profiles" / "one"
    profile.mkdir(parents=True)
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    client = Client()
    client.profile_dir = profile
    client.settings = SimpleNamespace(
        home=tmp_path, profile_subdir=lambda name: tmp_path / "profiles" / name
    )
    original = client.list_native_projects

    async def changed(*args, **kwargs):
        value = await original(*args, **kwargs)
        if phase == "discovery" or kwargs.get("include_catalogs"):
            marker.write_text("different@example.test")
        return value

    client.list_native_projects = changed
    with pytest.raises(Exception, match="identity changed"):
        await FlowApiClient.list_account_resources(client, kind="character")
    with sqlite3.connect(tmp_path / "native_inventory" / "account_resources.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        state = json.loads(conn.execute("SELECT state FROM checkpoints").fetchone()[0])
    assert state["pages"] == (1 if phase == "catalog" else 0)
    assert state["output_offset"] == 0 and state["token"] is None


def fake_client(seen):
    class ClientContext:
        def __init__(self, **kwargs):
            seen.append(("context", kwargs))
            self.profile_dir = kwargs["profile_dir"]
            self.settings = SimpleNamespace(
                home=self.profile_dir.parent,
                profile_subdir=lambda name: self.profile_dir.parent / name,
            )

        async def __aenter__(self):
            seen.append(("entered", {}))
            return self

        async def __aexit__(self, *args):
            pass

        async def list_account_resources(self, **kwargs):
            seen.append(("read", kwargs))
            return {"resources": [], "kind": kwargs["kind"], "complete": None}

    return ClientContext


@pytest.mark.parametrize("command", ["resources", "account-resources"])
def test_cli_registration_and_matching_controls(tmp_path, monkeypatch, command):
    from gflow_cli import cli_account_resources as cli
    from gflow_cli.cli_project import project

    seen = []
    monkeypatch.setattr(cli, "_resolve_profile", lambda value: "one")
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(profile_subdir=lambda name: tmp_path / name, headless=True),
    )
    monkeypatch.setattr(cli, "FlowApiClient", fake_client(seen))
    monkeypatch.setattr(cli, "run_with_handlers", lambda action, **kwargs: asyncio.run(action()))
    result = CliRunner().invoke(
        project,
        [
            command,
            "--kind",
            "voice",
            "--max-projects",
            "2",
            "--max-pages",
            "3",
            "--max-seconds",
            "4",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen[-1] == (
        "read",
        {"kind": "voice", "cursor": None, "max_projects": 2, "max_pages": 3, "max_seconds": 4},
    )


@pytest.mark.asyncio
async def test_direct_mcp_matching_controls_and_private_profile(tmp_path, monkeypatch):
    from gflow_cli.mcp import tools

    seen = []
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda value: "one")
    monkeypatch.setattr(
        tools,
        "get_settings",
        lambda: SimpleNamespace(profile_subdir=lambda name: tmp_path / name, headless=True),
    )
    monkeypatch.setattr(tools, "FlowApiClient", fake_client(seen))

    @asynccontextmanager
    async def lock(profile):
        yield

    monkeypatch.setattr(tools, "_profile_lock", lock)
    result = await tools.gflow_list_account_resources(
        kind="voice", profile="one", max_projects=2, max_pages=3, max_seconds=4
    )
    assert result["complete"] is None
    assert seen[-1] == (
        "read",
        {"kind": "voice", "cursor": None, "max_projects": 2, "max_pages": 3, "max_seconds": 4},
    )


@pytest.mark.asyncio
async def test_worker_branch_uses_sdk_mirror_without_project(tmp_path, monkeypatch):
    from gflow_cli.selfhost import native_worker as worker

    seen = []
    profile = tmp_path / "one"
    profile.mkdir()
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    monkeypatch.setattr(worker, "FlowApiClient", fake_client(seen))
    monkeypatch.setattr(worker.auth, "profile_dir", lambda profile: tmp_path / profile)
    result = await worker.execute(
        "account-resources",
        "one",
        {
            "kind": "voice",
            "max_projects": 2,
            "max_pages": 3,
            "max_seconds": 4,
            "expected_account_sha256": hashlib.sha256(b"operator@example.test").hexdigest(),
        },
    )
    assert result["status"] == "ok" and result["complete"] is None
    assert seen[-1] == (
        "read",
        {"kind": "voice", "cursor": None, "max_projects": 2, "max_pages": 3, "max_seconds": 4},
    )


def test_cli_invalid_cursor_reports_usage_before_profile_access(monkeypatch):
    from gflow_cli import cli_account_resources as cli
    from gflow_cli.cli_project import project

    monkeypatch.setattr(cli, "_resolve_profile", lambda value: pytest.fail("profile accessed"))
    result = CliRunner().invoke(
        project, ["resources", "--kind", "voice", "--cursor", "private-not-a-valid-cursor"]
    )
    assert result.exit_code == 2
    assert "private-not-a-valid-cursor" not in result.output


@pytest.mark.parametrize("mode", ["missing", "public", "symlink", "oversize"])
@pytest.mark.asyncio
async def test_sdk_requires_private_current_marker_before_native_access(tmp_path, mode):
    from gflow_cli.errors import ConfigurationError

    profile = tmp_path / "profiles" / "one"
    profile.mkdir(parents=True)
    marker = profile / ".gflow_account"
    if mode == "symlink":
        target = tmp_path / "marker-target"
        target.write_text("operator@example.test")
        target.chmod(0o600)
        marker.symlink_to(target)
    elif mode != "missing":
        marker.write_text("x" * 255 if mode == "oversize" else "operator@example.test")
        marker.chmod(0o644 if mode == "public" else 0o600)
    client = Client()
    client.profile_dir = profile
    client.settings = SimpleNamespace(
        home=tmp_path, profile_subdir=lambda name: tmp_path / "profiles" / name
    )
    with pytest.raises(ConfigurationError, match="current private identity"):
        await FlowApiClient.list_account_resources(client, kind="character")
    assert client.calls == [] and not (tmp_path / "native_inventory").exists()


@pytest.mark.parametrize("expected", [None, "invalid", "0" * 64])
@pytest.mark.asyncio
async def test_worker_expected_principal_binding_refuses_before_browser(
    tmp_path, monkeypatch, expected
):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost import native_worker as worker

    profile = tmp_path / "one"
    profile.mkdir()
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    seen = []
    monkeypatch.setattr(worker, "FlowApiClient", fake_client(seen))
    monkeypatch.setattr(worker.auth, "profile_dir", lambda name: profile)
    with pytest.raises(ConfigurationError):
        await worker.execute(
            "account-resources", "one", {"kind": "voice", "expected_account_sha256": expected}
        )
    assert not any(item[0] in {"entered", "read"} for item in seen)


@pytest.mark.asyncio
async def test_worker_dispatch_binding_survives_client_open_and_resets(tmp_path, monkeypatch):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost import native_worker as worker
    from gflow_cli.services.account_resources import account_resource_scope

    profile = tmp_path / "one"
    profile.mkdir()
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    seen = []

    class ChangedClient(fake_client(seen)):
        async def __aenter__(self):
            marker.write_text("different@example.test")
            return self

        async def list_account_resources(self, **kwargs):
            return await FlowApiClient.list_account_resources(self, **kwargs)

        async def list_native_projects(self, **kwargs):
            pytest.fail("native read after dispatch identity changed")

    monkeypatch.setattr(worker, "FlowApiClient", ChangedClient)
    monkeypatch.setattr(worker.auth, "profile_dir", lambda name: profile)
    with pytest.raises(ConfigurationError, match="dispatch identity changed"):
        await worker.execute(
            "account-resources",
            "one",
            {
                "kind": "voice",
                "expected_account_sha256": hashlib.sha256(b"operator@example.test").hexdigest(),
            },
        )
    assert not (tmp_path / "native_inventory").exists()
    client = ChangedClient(profile_dir=profile)
    assert account_resource_scope(client)[2] == "different@example.test"


@pytest.mark.asyncio
async def test_sdk_real_settings_maps_physical_profile_to_logical_scope(tmp_path):
    from gflow_cli.config import Settings

    settings = Settings(home=tmp_path)
    profile = settings.profile_subdir("pro2")
    assert profile.name == "profile_pro2"
    profile.mkdir(parents=True)
    marker = profile / ".gflow_account"
    marker.write_text("operator@example.test")
    marker.chmod(0o600)
    client = Client()
    client.profile_dir = profile
    client.settings = settings
    result = await FlowApiClient.list_account_resources(
        client, kind="character", max_projects=1, max_pages=1, max_seconds=7
    )
    assert result["resources"][0]["kind"] == "character"
    from gflow_cli.services.account_resources import account_resource_scope

    assert account_resource_scope(client) == (
        tmp_path / "native_inventory",
        "pro2",
        "operator@example.test",
    )
