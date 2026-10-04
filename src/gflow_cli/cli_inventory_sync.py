"""Project native inventory synchronization command."""

from __future__ import annotations

import click
from rich.console import Console

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers
from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError
from gflow_cli.profile_store import read_account_file
from gflow_cli.services.inventory_sync import sync_native_inventory


@click.command("sync")
@click.option("--profile", default=None, help="Configured account profile.")
@click.option(
    "--max-steps",
    default=10,
    type=click.IntRange(1, 100),
    show_default=True,
    help="Maximum native reads before saving resumable progress.",
)
@click.option(
    "--max-seconds",
    default=180,
    type=click.IntRange(1, 300),
    show_default=True,
    help="Run time bound; earlier verified reads remain committed.",
)
@click.option(
    "--restart",
    is_flag=True,
    help="Begin a fresh traversal while retaining all observed resources.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable progress.")
def sync_subcommand(
    profile: str | None, max_steps: int, max_seconds: int, restart: bool, as_json: bool
) -> None:
    """Resume native project catalogs and account history. Completeness stays unknown."""
    resolved = _resolve_profile(profile)

    async def act() -> None:
        settings = get_settings()
        account = read_account_file(settings.profile_subdir(resolved))
        if account is None:
            raise ConfigurationError(
                detail="Native inventory sync requires a recorded account identity"
            )
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            try:
                result = await sync_native_inventory(
                    client,
                    settings.home / "native_inventory",
                    profile=resolved,
                    account=account,
                    max_steps=max_steps,
                    max_seconds=max_seconds,
                    restart=restart,
                )
            except ValueError as exc:
                raise ConfigurationError(detail=str(exc)) from None
        if as_json:
            json_output.emit({"status": "ok", **result})
        else:
            Console().print(result)

    run_with_handlers(act, cli_command="project sync", as_json=as_json)
