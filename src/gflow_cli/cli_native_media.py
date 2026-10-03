"""Explicit free native upload and reversible archive commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.native_media import upload_snapshot_context, validate_archive, validate_upload
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.native_media import archive_media, upload_private_snapshot

console = Console()


@click.command("upload-video")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("--project", required=True)
@click.option("--rights-confirmed", is_flag=True, help="Assert rights for this upload only.")
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def upload_video_command(
    file: Path, project: str, rights_confirmed: bool, profile: str | None, as_json: bool
) -> None:
    """Upload an identified regular MP4 once; no generation or decoding claim."""
    try:
        project = validate_upload(project, rights_confirmed)
    except ConfigurationError as exc:
        raise click.UsageError(exc.detail) from None
    resolved = _resolve_profile(profile)

    async def act() -> None:
        result: dict[str, Any] = {}
        with upload_snapshot_context(
            file, project=project, rights_confirmed=rights_confirmed, outcome=result
        ) as private:
            result.update(await upload_private_snapshot(resolved, project, private))
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            console.print(f"Uploaded {result['media_id']}", markup=False)

    run_with_handlers(act, cli_command="project upload-video", as_json=as_json)


@click.command("archive")
@click.option("--project", required=True)
@click.option("--media-id", "media_ids", multiple=True, required=True)
@click.option(
    "--confirm-archive", is_flag=True, help="Confirm reversible whole-batch move to trash."
)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def archive_command(
    project: str,
    media_ids: tuple[str, ...],
    confirm_archive: bool,
    profile: str | None,
    as_json: bool,
) -> None:
    """Move complete owned native batches to trash; never deletes local files."""
    try:
        project, identifiers = validate_archive(project, media_ids, confirm_archive)
    except ConfigurationError as exc:
        raise click.UsageError(exc.detail) from None
    resolved = _resolve_profile(profile)

    async def act() -> None:
        result = await archive_media(resolved, project, identifiers)
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            for identifier in result["archived_media_ids"]:
                console.print(f"Archived {identifier}", markup=False)
            console.print("Reversible whole-batch move to trash.", markup=False)

    run_with_handlers(act, cli_command="project archive", as_json=as_json)


@click.command("delete-media")
@click.option("--project", required=True)
@click.option("--media-id", "media_ids", multiple=True, required=True)
@click.option("--confirm-delete", is_flag=True)
@click.option("--profile", default=None)
@click.option("--json", "as_json", is_flag=True)
def delete_media_command(
    project: str,
    media_ids: tuple[str, ...],
    confirm_delete: bool,
    profile: str | None,
    as_json: bool,
) -> None:
    """Permanently delete only these owned media identities; archive is separate."""
    from gflow_cli.api.transports.native_media_delete import validate_delete
    from gflow_cli.services.native_media import delete_media

    try:
        project, identifiers = validate_delete(project, media_ids, confirm_delete)
    except ValueError as error:
        raise click.UsageError(str(error)) from None
    resolved = _resolve_profile(profile)

    async def act() -> None:
        result = await delete_media(resolved, project, identifiers)
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            console.print("Permanently deleted " + ", ".join(result["deleted"]), markup=False)

    run_with_handlers(act, cli_command="project delete-media", as_json=as_json)
