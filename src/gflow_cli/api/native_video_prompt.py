"""Pure source-derived WI/VI video prompt encoding; no browser or billing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gflow_cli.api.native_video_audio import audio_wire_id, normalize_audio_reference
from gflow_cli.api.reference_markers import ReferenceSlot, TextSpan, resolve_reference_markers
from gflow_cli.errors import ConfigurationError


def encode_video_prompt(
    prompt: str,
    images: tuple[str, ...],
    audio: tuple[str, ...],
    characters: tuple[str, ...],
    reference_slots: Mapping[str, ReferenceSlot] | None = None,
) -> list[Any]:
    audio = tuple(normalize_audio_reference(value) for value in audio)
    slots = {f"referenceImage_{i}": ReferenceSlot("image", v) for i, v in enumerate(images, 1)}
    slots.update({f"referenceAudio_{i}": ReferenceSlot("audio", v) for i, v in enumerate(audio, 1)})
    slots.update(
        {f"character_{i}": ReferenceSlot("character", v) for i, v in enumerate(characters, 1)}
    )
    if reference_slots is not None:
        slots = {
            key: ReferenceSlot(
                slot.kind,
                normalize_audio_reference(slot.identifier)
                if slot.kind == "audio"
                else slot.identifier,
                slot.image_count,
            )
            for key, slot in reference_slots.items()
        }
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
            parts.append([None, [None, [audio_wire_id(span.identifier), ""]]])
        elif span.kind == "character":
            parts.append([None, [None, None, [span.identifier, ""]]])
        else:
            raise ConfigurationError(detail="Native reference video marker kind is unsupported")
    text: list[Any] = [None, None, [parts]]
    return text


def parse_video_slot_options(values: tuple[str, ...]) -> dict[str, str] | None:
    """CLI spelling of the existing native slot map; never reorder its keys."""
    if not values:
        return None
    slots: dict[str, str] = {}
    for value in values:
        key, separator, identifier = value.partition("=")
        if not separator or not identifier or key in slots:
            raise ConfigurationError(
                detail="Reference slots require distinct SLOT=REFERENCE values"
            )
        slots[key] = identifier
    return slots


def video_slot_inputs(
    prompt: str,
    images: tuple[str, ...],
    audio: tuple[str, ...],
    characters: tuple[str, ...],
    slot_ids: Mapping[str, str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], dict[str, ReferenceSlot] | None]:
    """Prepare explicit adapter slots; fresh classification remains in the SDK."""
    if slot_ids is None:
        return images, audio, characters, None
    if images or audio or characters or not slot_ids:
        raise ConfigurationError(
            detail="Explicit reference slots must replace image/audio/character reference lists"
        )
    slots = {
        key: ReferenceSlot(
            "audio"
            if key.startswith("referenceAudio_")
            else "character"
            if key.startswith("character_")
            else "image",
            normalize_audio_reference(value) if key.startswith("referenceAudio_") else value,
        )
        for key, value in slot_ids.items()
    }
    try:
        plan = resolve_reference_markers(prompt, surface="video", slots=slots)
    except ValueError:
        raise ConfigurationError(detail="Invalid or missing native video reference slot") from None
    return plan.image_ids, plan.audio_ids, plan.character_ids, slots
