"""`gflow character` — manage Flow Character entities (list / show / voices)."""

from __future__ import annotations

from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.markup import escape

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, _resolve_profile, run_with_handlers
from gflow_cli.api.character import (
    VOICES,
    Character,
    CharacterCreateResult,
    CharacterImageRequest,
)
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.config import get_settings
from gflow_cli.data.recorder import OperationRecorder
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.character_create import character_create
from gflow_cli.services.native_characters import (
    create_character_from_images as native_create_character_from_images,
)
from gflow_cli.services.native_characters import (
    update_character as native_update_character,
)
from gflow_cli.services.native_characters import (
    validate_create_inputs,
    validate_update_inputs,
)

console = Console()
log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Voice validation
# ---------------------------------------------------------------------------


def _normalize_voice(value: str | None) -> str | None:
    """Validate ``value`` against the voice catalog case-insensitively.

    Returns the canonical Capitalized voice name (so ``charon`` and ``Charon``
    both normalize to ``"Charon"``), or ``None`` when ``value`` is ``None``.

    Raises:
        click.BadParameter: when ``value`` is not a known voice. The message is
            language-agnostic and points at ``gflow character voices``.
    """
    if value is None:
        return None
    by_lower = {v.name.lower(): v.name for v in VOICES}
    canonical = by_lower.get(value.strip().lower())
    if canonical is None:
        raise click.BadParameter(
            f"unknown voice: {value!r} — run `gflow character voices` for valid names",
            param_hint="--voice",
        )
    return canonical


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


@click.group()
def character() -> None:
    """Manage Flow Character entities for a project."""


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@character.command("create")
@click.option("--project", "project_id", required=True, help="Flow project id.")
@click.option("--name", required=True, help="Display name for the new character.")
@click.option("--face-prompt", required=True, help="Prompt for the face reference image.")
@click.option(
    "--body-prompt",
    default=None,
    help=(
        "Body/clothing DESCRIPTION (optional). gflow wraps it in a "
        "self-contained front/side/back triptych instruction and seeds it with "
        "the generated face, so one generation yields all three angles. This is "
        "a description of the body and outfit, not a full prompt."
    ),
)
@click.option(
    "--voice",
    default=None,
    help="Preset voice name (e.g. Charon); case-insensitive. See `gflow character voices`.",
)
@click.option("--personality", default=None, help="Personality notes for the character.")
@click.option(
    "--model",
    type=click.Choice(["nano2", "nanopro"], case_sensitive=False),
    default="nano2",
    show_default=True,
    help="Character model: nano2 (Nano Banana 2, default) or nanopro (Nano Banana Pro).",
)
@click.option(
    "--format-prompt",
    is_flag=True,
    default=False,
    help=(
        "Click Flow's in-editor Format button and wait for Flow to rewrite the "
        "prompt into its character prompt-engineering shape before submitting. "
        "Flow rewrites server-side, so this adds a few seconds, and the reshaped "
        "prompt is longer and more detailed — which makes the generation itself "
        "slower too (measured: roughly double). Best-effort: if the button is "
        "missing, or the rewrite does not arrive in time, the prompt is submitted "
        "as typed and a warning names which of the two happened."
    ),
)
@click.option("--profile", default=None, help="Profile name (overrides default).")
@click.option(
    "--locale",
    default=None,
    help="BCP-47 locale for the character editor URL. Defaults to the ACCOUNT's own "
    "locale, resolved live from Flow (#580) — a hardcoded default sends non-en "
    "accounts to the wrong route and Flow bounces them back mid-prompt.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
def create(
    project_id: str,
    name: str,
    face_prompt: str,
    body_prompt: str | None,
    voice: str | None,
    personality: str | None,
    model: str,
    format_prompt: bool,
    profile: str | None,
    locale: str | None,
    as_json: bool,
) -> None:
    """Create a new Character entity in a project.

    Generates face (and optionally body) reference images, then persists and
    patches the entity.  Uses the persist-before-spend saga so a crashed run
    is recoverable.
    """
    voice = _normalize_voice(voice)
    profile_name = _resolve_profile(profile)
    pdir = _make_provider_dir(profile_name)
    settings = get_settings()
    run_with_handlers(
        lambda: _run_create(
            profile_name=profile_name,
            profile_dir=pdir,
            headless=settings.headless,
            project_id=project_id,
            name=name,
            face_prompt=face_prompt,
            body_prompt=body_prompt,
            voice=voice,
            personality=personality,
            model=model,
            format_prompt=format_prompt,
            locale=locale,
            as_json=as_json,
            settings=settings,
        ),
        cli_command="character create",
        as_json=as_json,
    )


async def _run_create(
    *,
    profile_name: str,
    profile_dir: Path,
    headless: bool,
    project_id: str,
    name: str,
    face_prompt: str,
    body_prompt: str | None,
    voice: str | None,
    personality: str | None,
    model: str,
    format_prompt: bool,
    locale: str | None,
    as_json: bool,
    settings: object,
) -> None:
    face = CharacterImageRequest(
        prompt=face_prompt,
        model=model,
        image_reference_index=0,
    )
    body: CharacterImageRequest | None = None
    if body_prompt is not None:
        body = CharacterImageRequest(
            prompt=body_prompt,
            model=model,
            image_reference_index=1,
        )

    async with FlowApiClient(profile_dir=profile_dir, headless=headless) as client:
        recorder = OperationRecorder.open(settings)  # type: ignore[arg-type]
        try:
            result: CharacterCreateResult = await character_create(
                client,
                recorder,
                profile_name=profile_name,
                profile_dir=profile_dir,
                project_id=project_id,
                name=name,
                face=face,
                body=body,
                voice=voice,
                personality=personality,
                locale=locale,
                format_prompt=format_prompt,
            )
        finally:
            recorder.close()

    if as_json:
        json_output.emit(
            {
                "status": "ok",
                "character": {
                    "entity_id": result.entity_id,
                    "project_id": result.project_id,
                    "name": result.name,
                    "workflow_ids": list(result.workflow_ids),
                    "primary_media_ids": list(result.primary_media_ids),
                    "voice": result.voice,
                    "image_paths": [str(p) if p is not None else None for p in result.image_paths],
                },
            }
        )
    else:
        console.print(f"[bold green]Character created:[/bold green] {result.entity_id}")
        for wf_id in result.workflow_ids:
            console.print(f"  workflow: {wf_id}")
        # Human-readable saved-image lines (slot 0 = face, slot 1 = body).
        slot_labels = ("face", "body")
        for slot, path in enumerate(result.image_paths):
            label = slot_labels[slot] if slot < len(slot_labels) else f"slot{slot}"
            console.print(f"  {label}: {path if path is not None else '(not saved)'}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@character.command("list")
@click.option("--project", "project_id", required=True, help="Flow project id.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
@click.option("--profile", default=None, help="Profile name (overrides default).")
def list_cmd(project_id: str, as_json: bool, profile: str | None) -> None:
    """List all Character entities in a project."""
    profile_name = _resolve_profile(profile)
    pdir = _make_provider_dir(profile_name)
    settings = get_settings()
    run_with_handlers(
        lambda: _run_list(
            profile_dir=pdir,
            headless=settings.headless,
            project_id=project_id,
            as_json=as_json,
        ),
        cli_command="character list",
        as_json=as_json,
    )


async def _run_list(*, profile_dir: Path, headless: bool, project_id: str, as_json: bool) -> None:
    async with FlowApiClient(profile_dir=profile_dir, headless=headless) as client:
        chars = await client.list_characters(project_id)
    if as_json:
        json_output.emit({"status": "ok", "characters": [_char_to_dict(c) for c in chars]})
    else:
        if not chars:
            console.print("[dim]No characters found.[/dim]")
            return
        for c in chars:
            _render_character_line(c)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@character.command("show")
@click.option("--project", "project_id", required=True, help="Flow project id.")
@click.option("--id", "entity_id", default=None, help="Character entity id.")
@click.option("--name", "name", default=None, help="Character display name (exact match).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
@click.option("--profile", default=None, help="Profile name (overrides default).")
def show(
    project_id: str,
    entity_id: str | None,
    name: str | None,
    as_json: bool,
    profile: str | None,
) -> None:
    """Show a single Character by --id or --name.

    Exactly one of --id or --name must be supplied.
    An ambiguous name (multiple characters share it) exits with code 11.
    """
    if entity_id is None and name is None:
        raise click.UsageError("Provide either --id or --name.")
    if entity_id is not None and name is not None:
        raise click.UsageError("--id and --name are mutually exclusive.")
    profile_name = _resolve_profile(profile)
    pdir = _make_provider_dir(profile_name)
    settings = get_settings()
    run_with_handlers(
        lambda: _run_show(
            profile_dir=pdir,
            headless=settings.headless,
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            as_json=as_json,
        ),
        cli_command="character show",
        as_json=as_json,
    )


async def _run_show(
    *,
    profile_dir: Path,
    headless: bool,
    project_id: str,
    entity_id: str | None,
    name: str | None,
    as_json: bool,
) -> None:
    async with FlowApiClient(profile_dir=profile_dir, headless=headless) as client:
        char = await client.get_character(project_id, entity_id=entity_id, name=name)
    if as_json:
        json_output.emit({"status": "ok", "character": _char_to_dict(char)})
    else:
        _render_character_detail(char)


# ---------------------------------------------------------------------------
# rm
# ---------------------------------------------------------------------------


@character.command("rm")
@click.option("--project", "project_id", required=True, help="Flow project id.")
@click.option("--id", "entity_id", default=None, help="Character entity id.")
@click.option("--name", "name", default=None, help="Character display name (exact match).")
@click.option("--yes", "-y", "assume_yes", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
@click.option("--profile", default=None, help="Profile name (overrides default).")
def rm(
    project_id: str,
    entity_id: str | None,
    name: str | None,
    assume_yes: bool,
    as_json: bool,
    profile: str | None,
) -> None:
    """Delete a Character by --id or --name.

    Exactly one of --id or --name must be supplied.  An ambiguous name (multiple
    characters share it) exits with code 11; use --id to disambiguate.  FREE —
    no reCAPTCHA, no credit.
    """
    if entity_id is None and name is None:
        raise click.UsageError("Provide either --id or --name.")
    if entity_id is not None and name is not None:
        raise click.UsageError("--id and --name are mutually exclusive.")
    profile_name = _resolve_profile(profile)
    pdir = _make_provider_dir(profile_name)
    settings = get_settings()
    run_with_handlers(
        lambda: _run_rm(
            profile_dir=pdir,
            headless=settings.headless,
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            assume_yes=assume_yes,
            as_json=as_json,
        ),
        cli_command="character rm",
        as_json=as_json,
    )


async def _run_rm(
    *,
    profile_dir: Path,
    headless: bool,
    project_id: str,
    entity_id: str | None,
    name: str | None,
    assume_yes: bool,
    as_json: bool,
) -> None:
    async with FlowApiClient(profile_dir=profile_dir, headless=headless) as client:
        char = await client.get_character(project_id, entity_id=entity_id, name=name)
        if not assume_yes and not as_json:
            click.confirm(
                f"Delete character {char.display_name!r} ({char.entity_id})?",
                abort=True,
            )
        await client.delete_characters(project_id, [char.entity_id])
    if as_json:
        json_output.emit(
            {
                "status": "ok",
                "deleted": {
                    "entity_id": char.entity_id,
                    "display_name": char.display_name,
                },
            }
        )
    else:
        click.echo(f"Deleted character {char.display_name!r} ({char.entity_id}).")


# ---------------------------------------------------------------------------
# Native existing-image creation and metadata updates (no portrait generation)
# ---------------------------------------------------------------------------


@character.command("create-from-images")
@click.option("--project", "project_id", required=True, help="Owning Flow project UUID.")
@click.option("--name", required=True, help="Character display name (1–200 characters).")
@click.option(
    "--image-reference-1", required=True, help="Existing owned image media UUID (portrait)."
)
@click.option(
    "--image-reference-2", default=None, help="Optional existing owned image UUID (body)."
)
@click.option("--personality", default=None, help="Optional notes, at most 2000 characters.")
@click.option(
    "--voice", default=None, help="Optional system preset name or owned saved audio UUID."
)
@click.option("--profile", default=None, help="Saved profile name.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
def create_from_images(
    project_id: str,
    name: str,
    image_reference_1: str,
    image_reference_2: str | None,
    personality: str | None,
    voice: str | None,
    profile: str | None,
    as_json: bool,
) -> None:
    """Copy existing project images into a saved character, without generating portraits.

    Inspect an unconfirmed mutation before retrying. Original images are preserved;
    this command is separate from the existing billed create saga.
    """
    voice = _normalize_voice(voice)
    try:
        validate_create_inputs(
            project_id, name, image_reference_1, image_reference_2, personality, voice
        )
    except ConfigurationError as exc:
        raise click.BadParameter(exc.detail) from None
    resolved = _resolve_profile(profile)

    async def execute() -> None:
        result = await native_create_character_from_images(
            profile=resolved,
            project_id=project_id,
            display_name=name,
            image_reference_1=image_reference_1,
            image_reference_2=image_reference_2,
            personality=personality,
            voice=voice,
        )
        if as_json:
            json_output.emit({"status": "ok", "character": _char_to_dict(result)})
        else:
            _render_character_detail(result)

    run_with_handlers(execute, cli_command="character create-from-images", as_json=as_json)


@character.command("update")
@click.option("--project", "project_id", required=True, help="Owning Flow project UUID.")
@click.option("--id", "entity_id", required=True, help="Owned character UUID.")
@click.option("--name", default=None, help="New display name (1–200 characters).")
@click.option("--personality", default=None, help="New notes; empty string clears them.")
@click.option(
    "--voice", default=None, help="Optional system preset name or owned saved audio UUID."
)
@click.option("--profile", default=None, help="Saved profile name.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
def update(
    project_id: str,
    entity_id: str,
    name: str | None,
    personality: str | None,
    voice: str | None,
    profile: str | None,
    as_json: bool,
) -> None:
    """Update name, notes or an owned preset/saved voice, without generation."""
    voice = _normalize_voice(voice)
    try:
        validate_update_inputs(project_id, entity_id, name, personality, voice)
    except ConfigurationError as exc:
        raise click.BadParameter(exc.detail) from None
    resolved = _resolve_profile(profile)

    async def execute() -> None:
        result = await native_update_character(
            profile=resolved,
            project_id=project_id,
            entity_id=entity_id,
            display_name=name,
            personality=personality,
            voice=voice,
        )
        if as_json:
            json_output.emit({"status": "ok", "character": _char_to_dict(result)})
        else:
            _render_character_detail(result)

    run_with_handlers(execute, cli_command="character update", as_json=as_json)


# ---------------------------------------------------------------------------
# voices
# ---------------------------------------------------------------------------


@character.command("voices")
@click.option(
    "--catalog", type=click.Choice(["bundled", "google"]), default="bundled", show_default=True
)
@click.option(
    "--project", "project_id", default=None, help="Required project UUID for native Google catalog."
)
@click.option("--profile", default=None, help="Owning profile for native Google catalog.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
def voices(as_json: bool, catalog: str, project_id: str | None, profile: str | None) -> None:
    """List bundled presets offline, or explicitly read the native system catalog."""
    if catalog == "google":
        if not is_uuid(project_id):
            raise click.BadParameter("Native project identifier must be a UUID")
        assert project_id is not None
        resolved = _resolve_profile(profile)
        settings = get_settings()

        async def execute() -> None:
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                snapshot = await client.list_native_voices(project_id)
            if as_json:
                json_output.emit({"status": "ok", **snapshot})
            else:
                for row in snapshot["voices"]:
                    console.print("{}  {}".format(row["name"], row["description"]), markup=False)
                console.print(snapshot["scope"], markup=False)

        run_with_handlers(execute, cli_command="character voices", as_json=as_json)
        return
    if project_id is not None:
        raise click.BadParameter("--project requires --catalog google")
    if as_json:
        json_output.emit(
            {
                "status": "ok",
                "voices": [
                    {"name": v.name, "description": v.description, "sample_url": v.sample_url}
                    for v in VOICES
                ],
            }
        )
    else:
        width = max(len(v.name) for v in VOICES)
        for v in VOICES:
            desc = v.description or "-"
            console.print(f"{v.name:<{width}}  {desc}  (sample: {v.sample_url})")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _char_to_dict(c: Character) -> dict[str, object]:
    return {
        "entity_id": c.entity_id,
        "display_name": c.display_name,
        "project_id": c.project_id,
        "workflow_ids": list(c.workflow_ids),
        "voice": c.voice,
        "personality": c.personality,
        "thumbnail_media_id": c.thumbnail_media_id,
    }


def _render_character_line(c: Character) -> None:
    wf_count = len(c.workflow_ids)
    voice_str = c.voice or "-"
    console.print(
        f"[bold]{escape(c.display_name)}[/bold]  "
        f"[dim]{c.entity_id}[/dim]  "
        f"voice={escape(voice_str)}  "
        f"refs={wf_count}"
    )


def _render_character_detail(c: Character) -> None:
    console.print(f"[bold green]Character:[/bold green] [bold]{escape(c.display_name)}[/bold]")
    console.print(f"  entity_id:  {c.entity_id}", markup=False)
    console.print(f"  project_id: {c.project_id}", markup=False)
    console.print(f"  voice:      {c.voice or '-'}", markup=False)
    console.print(f"  personality:{c.personality or '-'}", markup=False)
    console.print(f"  refs ({len(c.workflow_ids)}):")
    for wf in c.workflow_ids:
        console.print(f"    {wf}", markup=False)
