"""Pure source-derived WI/VI video prompt encoding; no browser or billing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gflow_cli.api.reference_markers import ReferenceSlot, TextSpan, resolve_reference_markers
from gflow_cli.errors import ConfigurationError


def encode_video_prompt(
    prompt: str,
    images: tuple[str, ...],
    audio: tuple[str, ...],
    characters: tuple[str, ...],
    reference_slots: Mapping[str, ReferenceSlot] | None = None,
) -> list[Any]:
    slots = {f"referenceImage_{i}": ReferenceSlot("image", v) for i, v in enumerate(images, 1)}
    slots.update({f"referenceAudio_{i}": ReferenceSlot("audio", v) for i, v in enumerate(audio, 1)})
    slots.update(
        {f"character_{i}": ReferenceSlot("character", v) for i, v in enumerate(characters, 1)}
    )
    if reference_slots is not None:
        slots = dict(reference_slots)
    try:
        plan = resolve_reference_markers(prompt, surface="video", slots=slots)
        if (plan.image_ids, plan.audio_ids, plan.character_ids) != (images, audio, characters):
            raise ValueError("Reference slot identities do not match ordered attachments")
    except ValueError:
        raise ConfigurationError(
            detail="Native video reference markers do not match supplied ingredients"
        ) from None
    # WI text1/reference2; VI media1/audio2. Both reference messages name1/handle2.
    # Deployed dKb permits an empty display handle; logical IDs remain authoritative.
    parts: list[Any] = []
    for span in plan.spans:
        if isinstance(span, TextSpan):
            if span.text:
                parts.append([span.text])
        elif span.kind == "image":
            parts.append([None, [[span.identifier, ""]]])
        elif span.kind == "audio":
            parts.append([None, [None, [span.identifier, ""]]])
        elif span.kind == "character":
            parts.append([None, [None, None, [span.identifier, ""]]])
        else:
            raise ConfigurationError(detail="Native reference video marker kind is unsupported")
    text: list[Any] = [None, None, [parts]]
    return text
