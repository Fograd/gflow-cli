"""Shared CLI/MCP local Auto approximation; explicit ratios remain unchanged."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gflow_cli.api.image import Aspect, ImageRef
from gflow_cli.api.image_aspect_policy import ImageAspectDecision, derive_aspect_from_file
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
