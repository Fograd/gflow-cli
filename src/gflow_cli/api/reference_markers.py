"""Pure useapi slot contracts; resolving a span does not attach it to Google.

Callers must verify ownership/count metadata and materialize every marker as a
measured native reference chunk. Plain text substitution is not grounding.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from gflow_cli.api.character import VOICES

if TYPE_CHECKING:
    from gflow_cli.api.image import GenerateImageRequest, ImageRef

Surface = Literal["image", "video"]
ReferenceKind = Literal["image", "character", "audio", "video"]


class ReferenceContractError(ValueError):
    """Safe slot/contract refusal, containing no submitted identifier or path."""


@dataclass(frozen=True)
class ReferenceSlot:
    kind: ReferenceKind
    identifier: str
    image_count: int | None = None  # verified snapshot metadata, never a user hint


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ReferenceMarker:
    start: int
    end: int
    slot: str
    kind: ReferenceKind
    identifier: str


@dataclass(frozen=True)
class BoundSlot:
    slot: str
    kind: ReferenceKind
    identifier: str
    image_count: int | None


@dataclass(frozen=True)
class ResolvedReferencePrompt:
    surface: Surface
    spans: tuple[TextSpan | ReferenceMarker, ...]
    slots: tuple[BoundSlot, ...]
    image_ids: tuple[str, ...]
    character_ids: tuple[str, ...]
    audio_ids: tuple[str, ...]
    video_ids: tuple[str, ...]

    @property
    def has_markers(self) -> bool:
        return any(isinstance(span, ReferenceMarker) for span in self.spans)


_FAMILIES: dict[Surface, dict[str, tuple[ReferenceKind, int]]] = {
    "image": {"reference": ("image", 10), "character": ("character", 7)},
    "video": {
        "referenceImage": ("image", 7),
        "character": ("character", 7),
        "referenceAudio": ("audio", 5),
        "referenceVideo": ("video", 1),
    },
}
# ASCII reserved syntax with Unicode word boundaries; embedded emails stay literal.
_TOKEN = re.compile(r"(?<![\w@])@([A-Za-z]+)_([0-9]+)(?!\w)")
_PRESETS = {voice.name.casefold(): voice.name for voice in VOICES}


def _identifier(value: object, kind: ReferenceKind) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or "\x00" in value:
        raise ReferenceContractError("Reference identifiers must be nonempty bounded strings")
    try:
        canonical = str(UUID(value))
        if canonical == value.lower():
            return canonical
    except ValueError:
        pass
    return _PRESETS.get(value.casefold(), value) if kind == "audio" else value


def resolve_reference_markers(
    prompt: object, *, surface: Surface, slots: Mapping[str, object]
) -> ResolvedReferencePrompt:
    """Preserve literal spans and all supplied attachments; repeat marker spans.

    This local conservative grammar reserves whole ASCII slot tokens only and
    does not implement escapes or undocumented substring matching. Body slot
    names use their documented exact case; marker case is insensitive.
    """
    if surface not in _FAMILIES:
        raise ReferenceContractError("Reference surface requires image or video")
    if not isinstance(prompt, str) or len(prompt) > 4000 or "\x00" in prompt:
        raise ReferenceContractError("Reference prompt must be at most 4000 characters without NUL")
    families = _FAMILIES[surface]
    names = {family.casefold(): family for family in families}
    canonical_slots: dict[str, tuple[ReferenceKind, int]] = {
        f"{family}_{index}": (kind, index)
        for family, (kind, cap) in families.items()
        for index in range(1, cap + 1)
    }
    if len(slots) > len(canonical_slots):
        raise ReferenceContractError("Too many reference body slots")
    bound: dict[str, BoundSlot] = {}
    ids: dict[ReferenceKind, list[str]] = {"image": [], "character": [], "audio": [], "video": []}
    counts: dict[str, int | None] = {}
    for slot, value in slots.items():
        if slot not in canonical_slots or not isinstance(value, ReferenceSlot):
            raise ReferenceContractError("Unsupported reference body slot")
        kind = canonical_slots[slot][0]
        if value.kind != kind:
            raise ReferenceContractError(f"{slot} has the wrong reference kind")
        identifier = _identifier(value.identifier, kind)
        if kind == "character" and identifier in counts and counts[identifier] != value.image_count:
            raise ReferenceContractError("Conflicting verified image count for one character")
        if kind == "character":
            counts[identifier] = value.image_count
        bound[slot] = BoundSlot(slot, kind, identifier, value.image_count)
        if identifier not in ids[kind]:
            ids[kind].append(identifier)
    spans: list[TextSpan | ReferenceMarker] = []
    cursor = 0
    for match in _TOKEN.finditer(prompt):
        family = names.get(match.group(1).casefold())
        if family is None:
            continue
        if family == "referenceVideo":
            raise ReferenceContractError("referenceVideo markers are not supported inline")
        index = match.group(2)
        if index.startswith("0") or len(index) > 2 or int(index) > families[family][1]:
            raise ReferenceContractError(f"{family} marker index is outside the supported slots")
        slot = f"{family}_{index}"
        selected = bound.get(slot)
        if selected is None:
            raise ReferenceContractError(f"'{slot}' was not provided in the request body")
        if match.start() > cursor:
            spans.append(TextSpan(cursor, match.start(), prompt[cursor : match.start()]))
        spans.append(
            ReferenceMarker(match.start(), match.end(), slot, selected.kind, selected.identifier)
        )
        cursor = match.end()
    if cursor < len(prompt) or not spans:
        spans.append(TextSpan(cursor, len(prompt), prompt[cursor:]))
    return ResolvedReferencePrompt(
        surface,
        tuple(spans),
        tuple(bound.values()),
        tuple(ids["image"]),
        tuple(ids["character"]),
        tuple(ids["audio"]),
        tuple(ids["video"]),
    )


def validate_reference_budget(
    plan: ResolvedReferencePrompt,
    *,
    surface: Surface,
    model: str,
    duration: int | None = None,
    start_image: bool = False,
    end_image: bool = False,
    native_image_cap: int | None = None,
) -> int:
    """Validate documented budgets using verified character image counts.

    A native cap may lower the image contract ceiling; this function never
    raises an unmeasured transport cap or verifies account ownership itself.
    """
    if plan.surface != surface:
        raise ReferenceContractError("Resolved reference surface does not match the budget surface")
    if duration is not None and type(duration) is not int:
        raise ReferenceContractError("Reference duration must be an integer")
    characters = {
        slot.identifier: slot.image_count for slot in plan.slots if slot.kind == "character"
    }
    total = len(plan.image_ids)
    for count in characters.values():
        if type(count) is not int or count < 1:
            raise ReferenceContractError("Each character requires a verified image count")
        total += count
    if native_image_cap is not None and (type(native_image_cap) is not int or native_image_cap < 0):
        raise ReferenceContractError("Native image budget must be a nonnegative integer")
    if surface == "image":
        if model not in {"nano-banana-2-lite", "nano-banana-2", "nano-banana-pro"}:
            raise ReferenceContractError("Unsupported image reference model")
        if plan.audio_ids or plan.video_ids or start_image or end_image:
            raise ReferenceContractError(
                "Image generation accepts image and character references only"
            )
        cap = min(10, native_image_cap) if native_image_cap is not None else 10
        if total > cap:
            raise ReferenceContractError(f"Image reference budget exceeded (maximum {cap})")
        return total
    if surface != "video":
        raise ReferenceContractError("Reference surface requires image or video")
    if model not in {
        "omni-flash",
        "veo-3.1-fast",
        "veo-3.1-lite",
        "veo-3.1-lite-low-priority",
        "veo-3.1-quality",
    }:
        raise ReferenceContractError("Unsupported video reference model")
    if end_image and not start_image:
        raise ReferenceContractError("End frame requires start frame")
    ingredients = bool(total or plan.audio_ids or plan.video_ids)
    if start_image and ingredients:
        raise ReferenceContractError("Video frames cannot be combined with reference ingredients")
    if plan.video_ids:
        if model != "omni-flash":
            raise ReferenceContractError("Video reference editing requires omni-flash")
        if duration is not None:
            raise ReferenceContractError("Video reference edits do not accept duration")
        if plan.character_ids:
            raise ReferenceContractError(
                "Character references are documented for R2V, not V2V edits"
            )
        image_cap, audio_cap = 5, 3
    elif model == "omni-flash":
        image_cap, audio_cap = 7, 5
    else:
        image_cap, audio_cap = (0, 0) if model == "veo-3.1-quality" else (3, 1)
        if ingredients and model == "veo-3.1-quality":
            raise ReferenceContractError("veo-3.1-quality does not support reference ingredients")
        if ingredients and duration not in (None, 8):
            raise ReferenceContractError("Veo reference ingredients require 8 seconds")
        for slot in plan.slots:
            if slot.slot.startswith("referenceImage_") and int(slot.slot.rsplit("_", 1)[1]) > 3:
                raise ReferenceContractError("Reference image slots 4–7 require omni-flash")
            if slot.slot.startswith("referenceAudio_") and not slot.slot.endswith("_1"):
                raise ReferenceContractError("Veo voice narration supports referenceAudio_1 only")
    if native_image_cap is not None:
        image_cap = min(image_cap, native_image_cap)
    if total > image_cap or len(plan.audio_ids) > audio_cap:
        raise ReferenceContractError(
            f"Video reference budget exceeded (images {image_cap}, voices {audio_cap})"
        )
    if plan.audio_ids and not total and not plan.video_ids:
        raise ReferenceContractError("Voice narration requires an image or character reference")
    return total


def prepare_image_slot_request(
    request: GenerateImageRequest, slots: Mapping[str, object]
) -> GenerateImageRequest:
    """Bind canonical slots without rewriting prompt or claiming native grounding.

    Existing media must exactly match ordered deduplicated image IDs. For local
    files, the caller supplies one managed decoded path per ordered logical ID;
    the native transport maps those IDs to measured uploaded media identities.
    Mixed existing-media/local-file attachment modes are not measured here.
    Character names and weighted image counts require fresh SDK preflight.
    """
    from dataclasses import replace

    plan = resolve_reference_markers(request.prompt, surface="image", slots=slots)
    if request.refs and request.ref_paths:
        raise ReferenceContractError("Mixed image attachment modes are not supported")
    resolved_refs = request.refs
    if request.refs:
        unique_refs: dict[str, ImageRef] = {}
        for ref in request.refs:
            identifier = _identifier(ref.name, "image")
            unique_refs.setdefault(identifier, replace(ref, name=identifier))
        resolved_refs = tuple(unique_refs.values())
        actual = tuple(unique_refs)
        if actual != plan.image_ids:
            raise ReferenceContractError("Reference plan does not match ordered image attachments")
    elif len(request.ref_paths) != len(plan.image_ids):
        raise ReferenceContractError("Reference plan does not match ordered image attachments")
    current_entities = tuple(
        dict.fromkeys(_identifier(value, "character") for value in request.reference_entities)
    )
    if current_entities and current_entities != plan.character_ids:
        raise ReferenceContractError("Reference plan does not match character attachments")
    return replace(
        request,
        refs=resolved_refs,
        reference_entities=plan.character_ids,
        reference_entity_names=(),
        reference_prompt_plan=plan,
    )


def validate_image_slot_plan(request: GenerateImageRequest) -> GenerateImageRequest:
    """Re-resolve supplied plans so SDK callers cannot bypass slot/prompt reconciliation."""
    plan = request.reference_prompt_plan
    if plan is None:
        return request
    prepared = prepare_image_slot_request(
        request,
        {
            slot.slot: ReferenceSlot(slot.kind, slot.identifier, slot.image_count)
            for slot in plan.slots
        },
    )
    if prepared.reference_prompt_plan != plan:
        raise ReferenceContractError("Reference plan does not match the submitted prompt")
    return prepared


def prepare_ordered_image_slots(request: GenerateImageRequest) -> GenerateImageRequest:
    """Enumerate explicit ordered CLI/MCP inputs; retain supplied native plan slots."""
    if request.reference_prompt_plan is not None:
        slots = {
            slot.slot: ReferenceSlot(slot.kind, slot.identifier, slot.image_count)
            for slot in request.reference_prompt_plan.slots
        }
    else:
        slots = {
            f"reference_{index}": ReferenceSlot("image", ref.name)
            for index, ref in enumerate(request.refs, 1)
        }
        if request.ref_paths:
            slots.update(
                {
                    f"reference_{index}": ReferenceSlot("image", f"local-reference-{index}")
                    for index in range(1, len(request.ref_paths) + 1)
                }
            )
        slots.update(
            {
                f"character_{index}": ReferenceSlot("character", entity)
                for index, entity in enumerate(request.reference_entities, 1)
            }
        )
    return prepare_image_slot_request(request, slots)


def reference_plan_record(plan: ResolvedReferencePrompt) -> dict[str, Any]:
    """JSON-compatible private plan record; no paths, credentials or rendered prose."""
    import json
    from dataclasses import asdict

    return cast(dict[str, Any], json.loads(json.dumps(asdict(plan))))


def decode_image_reference_plan(value: object, prompt: str) -> ResolvedReferencePrompt:
    """Rebuild types and re-resolve offsets; refuse unknown or tampered plan shapes."""
    if not isinstance(value, dict):
        raise ReferenceContractError("Serialized reference plan must be an object")
    raw = cast(dict[str, Any], value)
    expected = {"surface", "spans", "slots", "image_ids", "character_ids", "audio_ids", "video_ids"}
    if set(raw) != expected or raw["surface"] != "image":
        raise ReferenceContractError("Unsupported serialized image reference plan")
    if not isinstance(raw["slots"], list) or len(cast(list[Any], raw["slots"])) > 17:
        raise ReferenceContractError("Serialized reference slots exceed image limits")
    if not isinstance(raw["spans"], list) or len(cast(list[Any], raw["spans"])) > 8001:
        raise ReferenceContractError("Serialized reference spans exceed prompt limits")
    slots: dict[str, ReferenceSlot] = {}
    for entry in cast(list[Any], raw["slots"]):
        if not isinstance(entry, dict):
            raise ReferenceContractError("Serialized reference slot must be an object")
        item = cast(dict[str, Any], entry)
        if set(item) != {"slot", "kind", "identifier", "image_count"}:
            raise ReferenceContractError("Unsupported serialized reference slot")
        key, kind = item["slot"], item["kind"]
        if not isinstance(key, str) or key in slots or kind not in ("image", "character"):
            raise ReferenceContractError("Invalid serialized reference slot identity")
        count = item["image_count"]
        if count is not None and (type(count) is not int or not 1 <= count <= 10):
            raise ReferenceContractError("Invalid serialized reference image count")
        slots[key] = ReferenceSlot(cast(ReferenceKind, kind), item["identifier"], count)
    plan = resolve_reference_markers(prompt, surface="image", slots=slots)
    if reference_plan_record(plan) != raw:
        raise ReferenceContractError("Serialized reference plan does not match its prompt")
    return plan
