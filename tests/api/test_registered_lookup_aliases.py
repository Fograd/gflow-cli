import pytest

from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore
from gflow_cli.selfhost.native_resource_aliases import NativeResourceAlias, NativeResourceAliasStore
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
A = f"user:opaque-email:opaque-image:{M}"


@pytest.fixture
def registered(tmp_path, monkeypatch):
    root = tmp_path / "private"
    store = Store(root)
    store.account_set("pro2", "handle", P, True, True)
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(root))
    NativeAliasStore(root).register(NativeAlias(A, "pro2", "handle", P, M, "image"))
    return root


def test_exact_scoped_mapping(registered):
    from gflow_cli.api.registered_lookup import resolve_lookup

    binding = resolve_lookup("pro2", P, A, "media")
    assert binding.media_id == M
    for profile, project in [("pro3", P), ("pro2", W)]:
        with pytest.raises(ConfigurationError):
            resolve_lookup(profile, project, A, "media")


def test_unknown_alias_never_decoded(registered):
    from gflow_cli.api.registered_lookup import resolve_lookup

    with pytest.raises(ConfigurationError, match="registered"):
        resolve_lookup("pro2", P, A.replace("opaque-email", "unknown-email"), "media")


def test_disabled_account_refuses_mapping(registered):
    from gflow_cli.api.registered_lookup import resolve_lookup

    Store(registered).account_set("pro2", "handle", P, False, True)
    with pytest.raises(ConfigurationError):
        resolve_lookup("pro2", P, A, "media")


def test_voice_mapping_and_fresh_workflow(registered):
    from gflow_cli.api.registered_lookup import resolve_lookup, verify_resource

    alias = f"user:opaque-email:opaque-voice:{W}-mid:{M}"
    NativeResourceAliasStore(registered).register(
        NativeResourceAlias(alias, "pro2", "handle", P, "voice", M, W)
    )
    binding = resolve_lookup("pro2", P, alias, "voice")
    verify_resource(binding, {"ref": M, "project_id": P, "workflow_id": W})
    with pytest.raises(ConfigurationError):
        verify_resource(binding, {"ref": M, "project_id": P, "workflow_id": M})


def test_uuid_needs_no_selfhost_configuration(tmp_path, monkeypatch):
    from gflow_cli.api.registered_lookup import resolve_lookup

    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path / "absent"))
    assert resolve_lookup("pro2", P, M, "media") is None
    assert not (tmp_path / "absent").exists()


@pytest.mark.asyncio
async def test_sdk_alias_reads_canonical_id_and_verifies_kind(registered, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api import native_assets
    from gflow_cli.errors import WireFormatError

    client = SimpleNamespace(
        profile_dir=registered / "pro2",
        settings=SimpleNamespace(
            flow_host="flow.google.com", profile_subdir=lambda profile: registered / profile
        ),
        _checkout_page=AsyncMock(return_value=object()),
        _checkin_page=Mock(),
    )
    lookup = AsyncMock(return_value=SimpleNamespace(kind="image"))
    monkeypatch.setattr(native_assets, "lookup_asset", lookup)
    assert (await native_assets.get_native_asset(client, P, A)).kind == "image"
    assert lookup.await_args.kwargs["media_id"] == M
    lookup.return_value = SimpleNamespace(kind="video")
    with pytest.raises(WireFormatError):
        await native_assets.get_native_asset(client, P, A)
    assert client._checkin_page.call_count == 2


@pytest.mark.asyncio
async def test_unknown_alias_refuses_before_browser(registered):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api import native_assets

    client = SimpleNamespace(
        profile_dir=registered / "pro2",
        settings=SimpleNamespace(profile_subdir=lambda profile: registered / profile),
        _checkout_page=AsyncMock(),
    )
    with pytest.raises(ConfigurationError):
        await native_assets.get_native_asset(client, P, A.replace("opaque-email", "unknown-email"))
    client._checkout_page.assert_not_called()


def test_cli_alias_needs_explicit_profile(registered, monkeypatch):
    from click.testing import CliRunner

    from gflow_cli import cli_native_media
    from gflow_cli.cli import main

    monkeypatch.setattr(
        cli_native_media, "_resolve_profile", lambda value: pytest.fail("profile guessed")
    )
    result = CliRunner().invoke(main, ["project", "get-media", "--project", P, "--media-id", A])
    assert result.exit_code == 2 and "explicit --profile" in result.output


@pytest.mark.asyncio
async def test_mcp_alias_needs_explicit_profile(registered):
    from gflow_cli.mcp.tools import gflow_get_native_asset

    result = await gflow_get_native_asset(project=P, media_id=A)
    assert result["status"] == "error"
    assert "explicit profile" in str(result)


def test_character_declarations_checked_against_fresh_detail(registered):
    from gflow_cli.api.registered_lookup import resolve_lookup, verify_resource

    alias = f"user:opaque-email:opaque-character:{M}-imgs:1-voice:{W}"
    NativeResourceAliasStore(registered).register(
        NativeResourceAlias(
            alias, "pro2", "handle", P, "character", M, image_count=1, voice_workflow_id=W
        )
    )
    binding = resolve_lookup("pro2", P, alias, "character")
    detail = {
        "project_id": P,
        "entity_id": M,
        "image_references": [{}],
        "voice_detail": {"source": "user", "project_id": P, "workflow_id": W},
    }
    verify_resource(binding, detail)
    detail["image_references"] = []
    with pytest.raises(ConfigurationError):
        verify_resource(binding, detail)


def test_cli_registered_alias_reaches_shared_read(registered, monkeypatch):
    from unittest.mock import AsyncMock

    from click.testing import CliRunner

    from gflow_cli import cli_native_media
    from gflow_cli.cli import main
    from gflow_cli.services import native_assets

    monkeypatch.setattr(cli_native_media, "_resolve_profile", lambda profile: profile)
    read = AsyncMock(return_value={"mediaGenerationId": M, "kind": "image", "url": "private"})
    monkeypatch.setattr(native_assets, "read_asset", read)
    result = CliRunner().invoke(
        main,
        ["project", "get-media", "--project", P, "--media-id", A, "--profile", "pro2", "--json"],
    )
    assert result.exit_code == 0
    read.assert_awaited_once_with("pro2", P, A)


@pytest.mark.asyncio
async def test_mcp_registered_alias_reaches_shared_read(registered, monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from gflow_cli.mcp import tools
    from gflow_cli.services import native_assets

    @asynccontextmanager
    async def lock(profile):
        yield

    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: profile)
    monkeypatch.setattr(tools, "_profile_lock", lock)
    read = AsyncMock(return_value={"mediaGenerationId": M, "kind": "image", "url": "private"})
    monkeypatch.setattr(native_assets, "read_asset", read)
    result = await tools.gflow_get_native_asset(project=P, media_id=A, profile="pro2")
    assert result["status"] == "ok"
    read.assert_awaited_once_with("pro2", P, A)


@pytest.mark.parametrize("case", ["unknown", "foreign", "disabled"])
def test_cli_character_alias_refuses_before_browser(registered, monkeypatch, case):
    from click.testing import CliRunner

    from gflow_cli import cli_character
    from gflow_cli.cli import main

    alias = f"user:opaque-email:opaque-character:{M}-imgs:1"
    if case != "unknown":
        NativeResourceAliasStore(registered).register(
            NativeResourceAlias(alias, "pro2", "handle", P, "character", M, image_count=1)
        )
    if case == "disabled":
        Store(registered).account_set("pro2", "handle", P, False, True)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda value: value)
    monkeypatch.setattr(
        cli_character, "_make_provider_dir", lambda value: pytest.fail("profile opened")
    )
    result = CliRunner().invoke(
        main,
        [
            "character",
            "show",
            "--project",
            P,
            "--id",
            alias,
            "--profile",
            "pro3" if case == "foreign" else "pro2",
        ],
    )
    assert result.exit_code == 2
    assert "registered" in result.output.lower() or "selected" in result.output.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["unknown", "foreign", "disabled"])
async def test_mcp_character_alias_refuses_before_browser(registered, monkeypatch, case):
    from gflow_cli.mcp import tools

    alias = f"user:opaque-email:opaque-character:{M}-imgs:1"
    if case != "unknown":
        NativeResourceAliasStore(registered).register(
            NativeResourceAlias(alias, "pro2", "handle", P, "character", M, image_count=1)
        )
    if case == "disabled":
        Store(registered).account_set("pro2", "handle", P, False, True)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda value: value)
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: pytest.fail("browser opened"))
    result = await tools.gflow_character_show(
        project=P, entity_id=alias, profile="pro3" if case == "foreign" else "pro2"
    )
    assert result["status"] == "error"
