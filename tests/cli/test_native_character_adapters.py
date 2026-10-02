from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from gflow_cli import cli_character
from gflow_cli.api.character import Character
from gflow_cli.cli import main
from gflow_cli.mcp import tools

PROJECT = "11111111-1111-4111-8111-111111111111"
IMAGE = "22222222-2222-4222-8222-222222222222"
ENTITY = "33333333-3333-4333-8333-333333333333"
CHAR = Character(
    entity_id=ENTITY,
    display_name="Mira",
    project_id=PROJECT,
    workflow_ids=(),
    voice=None,
    personality=None,
    thumbnail_media_id=None,
)


def test_cli_create_from_images_dispatches_free_native_service(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(
        cli_character, "native_create_character_from_images", operation, raising=False
    )
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda p: "profile-one")
    result = CliRunner().invoke(
        main,
        [
            "character",
            "create-from-images",
            "--project",
            PROJECT,
            "--name",
            "Mira",
            "--image-reference-1",
            IMAGE,
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["character"]["entity_id"] == ENTITY
    operation.assert_awaited_once_with(
        profile="profile-one",
        project_id=PROJECT,
        display_name="Mira",
        image_reference_1=IMAGE,
        image_reference_2=None,
        personality=None,
        voice=None,
    )


def test_cli_update_allows_empty_notes_and_validates_before_profile(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(cli_character, "native_update_character", operation, raising=False)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda p: "profile-one")
    result = CliRunner().invoke(
        main,
        [
            "character",
            "update",
            "--project",
            PROJECT,
            "--id",
            ENTITY,
            "--personality",
            "",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    operation.assert_awaited_once_with(
        profile="profile-one",
        project_id=PROJECT,
        entity_id=ENTITY,
        display_name=None,
        personality="",
        voice=None,
    )


def test_cli_invalid_reference_never_resolves_profile(monkeypatch):
    def forbidden(p):
        pytest.fail("invalid input resolved a profile")

    monkeypatch.setattr(cli_character, "_resolve_profile", forbidden)
    result = CliRunner().invoke(
        main,
        [
            "character",
            "create-from-images",
            "--project",
            PROJECT,
            "--name",
            "Mira",
            "--image-reference-1",
            "bad-id",
            "--json",
        ],
    )
    assert result.exit_code != 0
    assert "image" in result.output.lower()


async def test_mcp_create_native_no_spend_does_not_block_free_copy(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(tools, "native_create_character_from_images", operation, raising=False)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "profile-one")
    monkeypatch.setenv("GFLOW_MCP_NO_SPEND", "1")
    result = await tools.gflow_character_create_from_images(
        project=PROJECT, display_name="Mira", image_reference_1=IMAGE
    )
    assert result["status"] == "ok"
    operation.assert_awaited_once()


async def test_mcp_update_native_metadata(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(tools, "native_update_character", operation, raising=False)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "profile-one")
    result = await tools.gflow_character_update(project=PROJECT, entity_id=ENTITY, personality="")
    assert result["character"]["entity_id"] == ENTITY
    assert operation.await_args.kwargs["personality"] == ""


async def test_mcp_rm_confirmation_required_before_profile(monkeypatch):
    def forbidden(p):
        pytest.fail("unconfirmed deletion resolved a profile")

    monkeypatch.setattr(tools, "_resolve_and_validate_profile", forbidden)
    result = await tools.gflow_character_rm(project=PROJECT, entity_id=ENTITY)
    assert result["status"] in ("error", "failed")
    assert "confirm" in str(result).lower()


async def test_mcp_invalid_create_never_resolves_profile(monkeypatch):
    def forbidden(p):
        pytest.fail("invalid create resolved a profile")

    monkeypatch.setattr(tools, "_resolve_and_validate_profile", forbidden)
    result = await tools.gflow_character_create_from_images(
        project=PROJECT, display_name="Mira", image_reference_1="bad-id"
    )
    assert result["status"] in ("error", "failed")


async def test_mcp_rm_pre_reads_owned_selector_before_delete(monkeypatch):
    client = AsyncMock()
    client.get_character.return_value = CHAR
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: context)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "profile-one")
    result = await tools.gflow_character_rm(project=PROJECT, name="Mira", confirm_delete=True)
    assert result["status"] == "ok"
    client.get_character.assert_awaited_once_with(PROJECT, entity_id=None, name="Mira")
    client.delete_characters.assert_awaited_once_with(PROJECT, [ENTITY])


async def test_mcp_create_unknown_preserves_partial_reference(monkeypatch):
    from gflow_cli.errors import CharacterMutationUnknownError

    operation = AsyncMock(
        side_effect=CharacterMutationUnknownError(
            project_id=PROJECT, operation="create", character_ref=ENTITY
        )
    )
    monkeypatch.setattr(tools, "native_create_character_from_images", operation)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "profile-one")
    result = await tools.gflow_character_create_from_images(
        project=PROJECT, display_name="Mira", image_reference_1=IMAGE
    )
    assert result["status"] in ("error", "failed")
    assert result["error"]["character_ref"] == ENTITY
    assert result["error"]["retryable"] is False
    operation.assert_awaited_once()


def test_cli_unknown_create_reports_exit40_and_partial_identity(monkeypatch):
    from gflow_cli.errors import CharacterMutationUnknownError

    operation = AsyncMock(
        side_effect=CharacterMutationUnknownError(
            project_id=PROJECT, operation="create", character_ref=ENTITY
        )
    )
    monkeypatch.setattr(cli_character, "native_create_character_from_images", operation)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda p: "profile-one")
    result = CliRunner().invoke(
        main,
        [
            "character",
            "create-from-images",
            "--project",
            PROJECT,
            "--name",
            "Mira",
            "--image-reference-1",
            IMAGE,
            "--json",
        ],
    )
    assert result.exit_code == 40, result.output
    assert ENTITY in result.output
    operation.assert_awaited_once()


@pytest.mark.parametrize(
    "options",
    [
        ["--name", ""],
        ["--personality", "x" * 2001],
    ],
)
def test_cli_update_invalid_input_does_not_resolve_profile(monkeypatch, options):
    def forbidden(profile):
        pytest.fail("invalid metadata resolved a profile")

    monkeypatch.setattr(cli_character, "_resolve_profile", forbidden)
    result = CliRunner().invoke(
        main, ["character", "update", "--project", PROJECT, "--id", ENTITY, *options, "--json"]
    )
    assert result.exit_code != 0


async def test_mcp_voice_only_update_passes_system_preset(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(tools, "native_update_character", operation)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda p: "profile-one")
    result = await tools.gflow_character_update(project=PROJECT, entity_id=ENTITY, voice="ChArOn")
    assert result["status"] == "ok"
    assert operation.await_args.kwargs["voice"] == "Charon"


@pytest.mark.parametrize("voice", ["unknown-preset", ""])
async def test_mcp_unknown_voice_rejected_before_profile(monkeypatch, voice):
    def forbidden(profile):
        pytest.fail("invalid voice resolved a profile")

    monkeypatch.setattr(tools, "_resolve_and_validate_profile", forbidden)
    result = await tools.gflow_character_update(project=PROJECT, entity_id=ENTITY, voice=voice)
    assert result["status"] in ("error", "failed")


def test_cli_voice_only_update_canonicalizes_preset(monkeypatch):
    operation = AsyncMock(return_value=CHAR)
    monkeypatch.setattr(cli_character, "native_update_character", operation)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda p: "profile-one")
    result = CliRunner().invoke(
        main,
        [
            "character",
            "update",
            "--project",
            PROJECT,
            "--id",
            ENTITY,
            "--voice",
            "cHaRoN",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert operation.await_args.kwargs["voice"] == "Charon"


def test_cli_unknown_voice_rejected_before_profile(monkeypatch):
    def forbidden(profile):
        pytest.fail("invalid voice resolved a profile")

    monkeypatch.setattr(cli_character, "_resolve_profile", forbidden)
    result = CliRunner().invoke(
        main,
        [
            "character",
            "update",
            "--project",
            PROJECT,
            "--id",
            ENTITY,
            "--voice",
            "unknown-preset",
            "--json",
        ],
    )
    assert result.exit_code != 0


@pytest.mark.parametrize("operation", ["create-from-images", "update"])
def test_confirmed_native_mutation_renders_literal_brackets(monkeypatch, operation):
    from dataclasses import replace

    name = "[/bold]Literal character[bold]"
    notes = "[/red]literal personality"
    confirmed = replace(CHAR, display_name=name, personality=notes)
    called = AsyncMock(return_value=confirmed)
    symbol = (
        "native_create_character_from_images"
        if operation == "create-from-images"
        else "native_update_character"
    )
    monkeypatch.setattr(cli_character, symbol, called)
    monkeypatch.setattr(cli_character, "_resolve_profile", lambda p: "profile-one")
    args = ["character", operation, "--project", PROJECT, "--name", name, "--personality", notes]
    args += (
        ["--image-reference-1", IMAGE] if operation == "create-from-images" else ["--id", ENTITY]
    )
    result = CliRunner().invoke(main, args)
    called.assert_awaited_once()
    assert result.exit_code == 0, result.output
    assert name in result.output
    assert notes in result.output


def test_character_list_line_renders_literal_brackets(capsys):
    from dataclasses import replace

    name = "[/bold]Literal character[bold]"
    cli_character._render_character_line(replace(CHAR, display_name=name))
    assert name in capsys.readouterr().out
