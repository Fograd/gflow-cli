"""Fresh native image reference model budgets."""

from __future__ import annotations

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _resolve_profile, run_with_handlers


@click.command("reference-models")
@click.option("--project", required=True)
@click.option("--profile", default="default")
@click.option("--json", "as_json", is_flag=True)
def image_reference_models_command(project: str, profile: str, as_json: bool) -> None:
    """Read advertised and effective image reference limits; no generation."""
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.config import get_settings

    resolved = _resolve_profile(profile)

    async def action() -> None:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(resolved), headless=False
        ) as client:
            models = await client.list_native_image_reference_models(project)
        if as_json:
            json_output.emit({"models": models, "source": "native-account-model-metadata"})
        else:
            for item in models:
                click.echo(
                    f"{item['model_key']} advertised={item['advertised_reference_cap']} "
                    f"effective={item['effective_reference_cap']}"
                )

    run_with_handlers(action, cli_command="image reference-models", as_json=as_json)
