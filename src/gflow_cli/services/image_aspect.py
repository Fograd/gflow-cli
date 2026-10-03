"""Shared CLI/MCP local Auto approximation; explicit ratios remain unchanged."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from gflow_cli.api.image import Aspect, ImageRef
from gflow_cli.api.image_aspect_policy import (
    ImageAspectDecision,
    derive_aspect,
    derive_aspect_from_file,
)
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import ConfigurationError


def resolve_image_aspect(
    aspect: str, ordered_refs: Sequence[Path | ImageRef]
) -> tuple[Aspect, ImageAspectDecision | None]:
    """Decode only the first actual local reference, before browser/generation actions.

    References retain caller input/numeric-slot ordering. Never skip an unresolved
    native ID to derive from a later file; character-only inputs cannot satisfy Auto.
    This policy does not send or imply a native Google Auto enum.
    """
    if aspect != "auto":
        return Aspect.from_cli(aspect), None
    if not ordered_refs or not isinstance(ordered_refs[0], Path):
        raise ConfigurationError(
            detail="Auto requires the first reference to be a resolvable local PNG or JPEG image",
            remediation_hint="Supply a local image first, or choose an explicit ratio for IDs",
        )
    try:
        decision = derive_aspect_from_file(ordered_refs[0])
    except ValueError as exc:
        raise ConfigurationError(
            detail="Auto requires a valid bounded local PNG or JPEG reference"
        ) from exc
    return Aspect.from_cli(decision.resolved_aspect), decision


def aspect_decision_metadata(decision: ImageAspectDecision | None) -> dict[str, str]:
    """Preserve the approximation decision in public and queued result metadata."""
    if decision is None:
        return {}
    return {
        "requestedAspectRatio": decision.requested_aspect,
        "resolvedAspectRatio": decision.resolved_aspect,
        "aspectPolicy": decision.policy,
    }


if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


async def resolve_native_image_aspect(
    client: FlowApiClient, project_id: str, media_id: str
) -> tuple[Aspect, ImageAspectDecision]:
    """Derive Auto from one fresh, active same-project typed image snapshot.

    No generation, token mint, signed URL download or caption fallback occurs.
    Missing dimensions remain an explicit refusal, never an invented ratio.
    """
    if not is_uuid(project_id) or not is_uuid(media_id):
        raise ConfigurationError(detail="Native Auto requires project and image UUIDs")
    if client.settings.flow_host == "labs.google":
        raise ConfigurationError(detail="Native Auto requires the migrated Flow host")
    project_id, media_id = str(UUID(project_id)), str(UUID(media_id))
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        payload = await read_project_payload(page, project_id)
        rows = parse_media_snapshot(payload, project_id)["media"]
        matches = [row for row in rows if row["media_id"].lower() == media_id.lower()]
        if len(matches) != 1 or matches[0]["kind"] != "image":
            raise ValueError("First reference is not one owned typed image")
        image = matches[0]
        states = [
            row
            for row in project_media(payload, project_id)
            if row["workflow_id"] == image["workflow_id"]
        ]
        if (
            len(states) != 1
            or states[0]["archived"] is not False
            or states[0]["project_id"] != project_id
            or (
                states[0]["media_id"] != media_id
                and media_id not in states[0].get("batch_media_ids", [])
            )
        ):
            raise ValueError("First reference image is not uniquely active")
        width, height = image.get("width"), image.get("height")
        decision = derive_aspect(width, height)
        if width * height > 25_000_000:
            raise ValueError("First native image exceeds the decode pixel limit")
        return Aspect.from_cli(decision.resolved_aspect), decision
    except (ValueError, TypeError, KeyError):
        raise ConfigurationError(
            detail="Native Auto requires fresh active owned image dimensions",
            remediation_hint="Choose an explicit ratio when native dimensions are unavailable",
        ) from None
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
