"""`gflow project` subcommand group — project lifecycle & dual-side title sync."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import click
import structlog
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import (
    _make_provider_dir,
    _resolve_profile,
    _validate_project_id,
    run_with_handlers,
)
from gflow_cli.api import routes
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import validate_project_traversal
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.cli_data import _db_path, _emit_projects_table
from gflow_cli.config import get_settings
from gflow_cli.data.models import ProjectRecord
from gflow_cli.data.queries import list_projects
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.profile_store import account_locale_for
from gflow_cli.project_output import local_project_payload

if TYPE_CHECKING:
    from pathlib import Path

console = Console()
logger = structlog.get_logger(__name__)


@click.group()
def project() -> None:
    """Manage Google Flow projects."""


@project.command("list")
@click.option("--profile", default=None, help="Profile name to filter projects by.")
@click.option(
    "--limit", default=50, show_default=True, type=int, help="Maximum projects to return."
)
@click.option(
    "--source", type=click.Choice(["local", "google"]), default="local", show_default=True
)
@click.option("--cursor", default=None, help="Opaque Google project page cursor.")
@click.option(
    "--all-pages", is_flag=True, help="Traverse Google project pages within bounded limits."
)
@click.option(
    "--max-pages",
    default=None,
    type=click.IntRange(1, 100),
    help="Page cap with --all-pages; default 100.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON output.")
@click.pass_context
def list_subcommand(
    ctx: click.Context,
    profile: str | None,
    limit: int,
    source: str,
    cursor: str | None,
    all_pages: bool,
    max_pages: int | None,
    as_json: bool,
) -> None:
    """List local projects or bounded read-only Google account pages."""
    try:
        validate_project_traversal(all_pages, max_pages)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from None
    if source != "google" and (all_pages or max_pages is not None):
        raise click.BadParameter("Traversal controls require --source google")
    if source == "google":
        if ctx.get_parameter_source("limit") != click.core.ParameterSource.DEFAULT:
            raise click.BadParameter("Google pages have a fixed size of 21; omit --limit")
        if cursor is not None and (not cursor or len(cursor) > 4096):
            raise click.BadParameter("Google cursor must contain 1–4096 characters")
        resolved = _resolve_profile(profile)

        async def act() -> None:
            settings = get_settings()
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                snapshot = (
                    await client.list_native_projects(
                        cursor=cursor, all_pages=all_pages, max_pages=max_pages
                    )
                    if all_pages
                    else await client.list_native_projects(cursor=cursor)
                )
            if as_json:
                json_output.emit({"status": "ok", **snapshot})
            else:
                for row in snapshot["projects"]:
                    console.print(f"{row['project_id']}  {row['name']}", markup=False)
                console.print(f"Next cursor: {snapshot['next_cursor'] or '(none)'}", markup=False)
                if all_pages:
                    state = (
                        "exhausted" if snapshot.get("pagination_exhausted") else "page cap reached"
                    )
                    console.print(f"Traversal: {state}; pages read: {snapshot.get('pages_read')}")
                console.print("Snapshot completeness: unknown")

        run_with_handlers(act, cli_command="project list", as_json=as_json)
        return
    if cursor is not None:
        raise click.BadParameter("--cursor requires --source google")
    db_path = _db_path()
    resolved_profile = _resolve_profile(profile) if profile else None
    rows = list_projects(
        db_path=db_path,
        profile=resolved_profile,
        limit=limit,
        offset=0,
    )
    if as_json:
        json_output.emit(
            {
                "status": "ok",
                "projects": [local_project_payload(row) for row in rows],
                "total": len(rows),
            }
        )
    else:
        _emit_projects_table(rows)


@project.command("media")
@click.option("--project", "project_id", required=True, callback=_validate_project_id)
@click.option("--source", type=click.Choice(["google"]), default="google", show_default=True)
@click.option("--profile", default=None, help="Profile owning the native project.")
@click.option("--json", "as_json", is_flag=True, help="Emit a read-only native timeline snapshot.")
def media_subcommand(project_id: str, source: str, profile: str | None, as_json: bool) -> None:
    """Read native project media; does not sync or remove catalog entries."""
    if not is_uuid(project_id):
        raise click.BadParameter("Native project identifier must be a UUID")
    resolved = _resolve_profile(profile)

    async def act() -> None:
        settings = get_settings()
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            snapshot = await client.list_native_media(project_id)
        if as_json:
            json_output.emit({"status": "ok", **snapshot})
        else:
            for row in snapshot["media"]:
                console.print(f"{row['media_id']}  kind={row['kind'] or 'unknown'}")
            console.print("Snapshot completeness: unknown; no catalog changes")

    run_with_handlers(act, cli_command="project media", as_json=as_json)


@project.command("show")
@click.argument("project_id", callback=_validate_project_id)
@click.option("--profile", default=None, help="Profile name.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON output.")
def show_subcommand(project_id: str, profile: str | None, as_json: bool) -> None:
    """Show details of a recorded project by project ID."""
    db_path = _db_path()
    resolved_profile = _resolve_profile(profile) if profile else None
    repo = DataRepository(DataStore.open(db_path))
    record = repo.get_project(resolved_profile, project_id)
    if record is None:
        if as_json:
            json_output.emit(
                {
                    "status": "error",
                    "error": {
                        "title": "Project Not Found",
                        "detail": f"No project found with ID {project_id!r}",
                        "status": 404,
                    },
                }
            )
            raise SystemExit(1)
        console.print(f"[yellow]Project not found:[/yellow] {project_id}")
        raise SystemExit(1)

    url = routes.project_editor_url_or_none(
        account_locale_for(record.profile_name), record.flow_project_id
    )
    if as_json:
        json_output.emit(
            {
                "status": "ok",
                "project": {
                    "id": record.id,
                    "flow_project_id": record.flow_project_id,
                    "title": record.title,
                    "profile": record.profile_name,
                    "source": record.source,
                    "created_at": record.created_at,
                    "url": url,
                },
            }
        )
    else:
        console.print(f"[bold]Project ID:[/bold] {record.flow_project_id}")
        console.print(f"[bold]Title:[/bold] {record.title or '<unnamed>'}")
        console.print(f"[bold]Profile:[/bold] {record.profile_name}")
        console.print(f"[bold]Source:[/bold] {record.source}")
        if record.created_at:
            console.print(f"[bold]Created:[/bold] {record.created_at}")
        if url:
            # soft_wrap: without it Rich folds the URL at the terminal width,
            # leaving a dangling "URL:" label and a link broken for copy-paste
            # and for `| grep URL`.
            console.print(f"[bold]URL:[/bold] {url}", soft_wrap=True)


async def _run_create_project(
    profile_name: str,
    provider_dir: Path,
    title: str | None,
) -> tuple[str, str]:
    async with FlowApiClient(profile_dir=provider_dir) as client:
        info = await client.create_project(title=title)
        repo = DataRepository(DataStore.open(_db_path()))
        repo.upsert_profile(profile_name, provider_dir)
        rec = ProjectRecord(
            id=str(uuid.uuid4()),
            profile_name=profile_name,
            flow_project_id=info.project_id,
            title=info.title,
            source="gflow-cli",
        )
        repo.upsert_project(rec)
        return info.project_id, info.title


@project.command("create")
@click.option("--name", "--title", "--project-name", "title", default=None, help="Project title.")
@click.option("--profile", default=None, help="Profile name.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON output.")
def create_subcommand(title: str | None, profile: str | None, as_json: bool) -> None:
    """Create a fresh Flow project with dual-side title synchronization."""
    profile_name = _resolve_profile(profile)
    provider_dir = _make_provider_dir(profile_name)

    async def _act() -> None:
        project_id, project_title = await _run_create_project(profile_name, provider_dir, title)
        if as_json:
            json_output.emit(
                {
                    "status": "ok",
                    "project_id": project_id,
                    "title": project_title,
                    "profile": profile_name,
                }
            )
        else:
            console.print(
                f"[green]Project created:[/green] [bold]{project_id}[/bold] "
                f"(title: {project_title})"
            )

    run_with_handlers(_act, cli_command="project create", as_json=as_json)


async def _run_rename_project(
    profile_name: str,
    provider_dir: Path,
    project_id: str,
    new_title: str,
) -> None:
    async with FlowApiClient(profile_dir=provider_dir) as client:
        await client.rename_project(project_id, new_title)
        repo = DataRepository(DataStore.open(_db_path()))
        repo.upsert_profile(profile_name, provider_dir)
        repo.update_project_title(profile_name, project_id, new_title)


@project.command("rename")
@click.argument("project_id", callback=_validate_project_id)
@click.argument("new_title")
@click.option("--profile", default=None, help="Profile name.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON output.")
def rename_subcommand(project_id: str, new_title: str, profile: str | None, as_json: bool) -> None:
    """Rename a Flow project with dual-side title synchronization."""
    profile_name = _resolve_profile(profile)
    provider_dir = _make_provider_dir(profile_name)

    async def _act() -> None:
        await _run_rename_project(profile_name, provider_dir, project_id, new_title)
        if as_json:
            json_output.emit(
                {
                    "status": "ok",
                    "project_id": project_id,
                    "title": new_title,
                    "profile": profile_name,
                }
            )
        else:
            console.print(
                f"[green]Renamed project[/green] [bold]{project_id}[/bold] "
                f"to '[bold]{new_title}[/bold]'"
            )

    run_with_handlers(_act, cli_command="project rename", as_json=as_json)


from gflow_cli.cli_native_media import (  # noqa: E402
    archive_command,
    delete_media_command,
    download_media_command,
    get_media_command,
    upload_video_command,
)  # noqa: E402

project.add_command(upload_video_command)
project.add_command(archive_command)

project.add_command(delete_media_command)

project.add_command(get_media_command)
project.add_command(download_media_command)
