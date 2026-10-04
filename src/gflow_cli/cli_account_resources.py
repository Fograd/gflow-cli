"""Explicit observed account resource read extension."""

from __future__ import annotations

import click
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings


@click.command("resources")
@click.option("--kind", required=True, type=click.Choice(["character", "voice"]))
@click.option("--cursor", default=None, help="Opaque continuation from the previous result.")
@click.option("--max-projects", default=10, type=click.IntRange(1, 20), show_default=True)
@click.option("--max-pages", default=1, type=click.IntRange(1, 100), show_default=True)
@click.option("--max-seconds", default=180, type=click.IntRange(1, 180), show_default=True)
@click.option("--profile", default=None, help="Configured verified account profile.")
@click.option("--json", "as_json", is_flag=True)
def resources_subcommand(
    kind: str,
    cursor: str | None,
    max_projects: int,
    max_pages: int,
    max_seconds: int,
    profile: str | None,
    as_json: bool,
) -> None:
    """Read observed characters or saved voices across bounded project catalogs."""
    from typing import cast

    from gflow_cli.services.account_resources import ResourceKind, validate_account_resource_options

    try:
        validate_account_resource_options(kind, cursor, max_projects, max_pages, max_seconds)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from None
    resolved = _resolve_profile(profile)

    async def act() -> None:
        settings = get_settings()
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            result = await client.list_account_resources(
                kind=cast(ResourceKind, kind),
                cursor=cursor,
                max_projects=max_projects,
                max_pages=max_pages,
                max_seconds=max_seconds,
            )
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            Console().print(result)

    run_with_handlers(act, cli_command="project resources", as_json=as_json)
