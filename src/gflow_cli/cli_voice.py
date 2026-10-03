"""Saved native TTS commands, separate from system preset lookup."""

from __future__ import annotations

from typing import Any, Literal

import click
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.native_voices import validate_create
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.native_voices import saved_voice_operation

console = Console()


@click.group("voice")
def voice_group() -> None:
    """List, inspect, generate and delete saved preset-based speech."""


def _run(
    operation: Literal["list", "get", "create", "delete"],
    project: str,
    profile: str | None,
    as_json: bool,
    **kwargs: Any,
) -> None:
    try:
        project = validate_identifier(project)
        if operation in {"get", "delete"}:
            kwargs["voice_id"] = validate_identifier(kwargs["voice_id"])
        if operation == "create":
            validate_create(
                project,
                kwargs["display_name"],
                kwargs["preset_voice"],
                kwargs["dialog"],
                kwargs["performance"],
            )
        if operation == "delete" and kwargs.get("confirm_delete") is not True:
            raise ValueError("Saved voice deletion requires --confirm-delete")
    except (ValueError, ConfigurationError) as error:
        raise click.UsageError(str(error)) from None
    resolved = _resolve_profile(profile)

    async def act() -> None:
        result = await saved_voice_operation(
            profile=resolved, operation=operation, project_id=project, **kwargs
        )
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            if operation == "list":
                for row in result["voices"]:
                    console.print(row["ref"] + " " + row["display_name"], markup=False)
            else:
                console.print(result.get("ref", result.get("deleted", [])), markup=False)

    run_with_handlers(act, cli_command="voice " + operation, as_json=as_json)


@voice_group.command("list")
@click.option("--project", required=True)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def list_command(project: str, profile: str | None, as_json: bool) -> None:
    """Read the selected-project saved voice snapshot."""
    _run("list", project, profile, as_json)


@voice_group.command("show")
@click.option("--project", required=True)
@click.option("--id", "voice_id", required=True)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def show_command(project: str, voice_id: str, profile: str | None, as_json: bool) -> None:
    """Read owned saved voice metadata and its available fresh playback URL."""
    _run("get", project, profile, as_json, voice_id=voice_id)


@voice_group.command("create")
@click.option("--project", required=True)
@click.option("--name", "display_name", required=True)
@click.option("--preset", "preset_voice", required=True)
@click.option("--dialog", required=True)
@click.option("--performance", required=True)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def create_command(
    project: str,
    display_name: str,
    preset_voice: str,
    dialog: str,
    performance: str,
    profile: str | None,
    as_json: bool,
) -> None:
    """Generate speech once and save it; this operation can consume credits."""
    _run(
        "create",
        project,
        profile,
        as_json,
        display_name=display_name,
        preset_voice=preset_voice,
        dialog=dialog,
        performance=performance,
    )


@voice_group.command("rm")
@click.option("--project", required=True)
@click.option("--id", "voice_id", required=True)
@click.option("--confirm-delete", is_flag=True)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def delete_command(
    project: str,
    voice_id: str,
    confirm_delete: bool,
    profile: str | None,
    as_json: bool,
) -> None:
    """Delete this owned saved voice once; preserve unknown acknowledgement."""
    _run("delete", project, profile, as_json, voice_id=voice_id, confirm_delete=confirm_delete)
