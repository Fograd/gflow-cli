"""Strict native positional image grounding; unknown chunk shapes fail closed."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast

from gflow_cli.api.reference_markers import ReferenceMarker, ResolvedReferencePrompt, TextSpan
from gflow_cli.api.transports.image_entity_grounding import image_submit_rows

if TYPE_CHECKING:
    from playwright.async_api import Page

    from gflow_cli.api.transports.migrated_composer import MigratedComposer


@dataclass(frozen=True)
class NativePromptChunk:
    kind: Literal["text", "image", "character"]
    value: str
    name: str = ""


def _chunks(value: Any) -> tuple[NativePromptChunk, ...]:
    if not isinstance(value, list) or len(cast(list[Any], value)) != 1:
        raise ValueError("Unmeasured paragraph grouping")
    chunks: list[NativePromptChunk] = []
    for raw in cast(list[Any], value)[0]:
        if not isinstance(raw, list):
            raise ValueError("Unknown native prompt chunk")
        row = cast(list[Any], raw)
        if len(row) == 1 and isinstance(row[0], str):
            chunks.append(NativePromptChunk("text", row[0]))
        elif len(row) == 2 and row[0] is None and isinstance(row[1], list):
            arm = cast(list[Any], row[1])
            if len(arm) == 1 and isinstance(arm[0], list):
                kind = "image"
                pair = cast(list[Any], arm[0])
            elif len(arm) == 3 and arm[:2] == [None, None] and isinstance(arm[2], list):
                kind = "character"
                pair = cast(list[Any], arm[2])
            else:
                raise ValueError("Unknown native reference arm")
            if len(pair) != 2 or not all(isinstance(item, str) for item in pair):
                raise ValueError("Unknown native reference identity")
            chunks.append(NativePromptChunk(kind, pair[0], pair[1]))
        else:
            raise ValueError("Unknown native prompt chunk")
    return tuple(chunks)


def _vector(value: Any, *, media: bool) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("Unknown native reference vector")
    ids: list[str] = []
    for raw in cast(list[Any], value):
        if not isinstance(raw, list):
            raise ValueError("Unknown native vector row")
        row = cast(list[Any], raw)
        if len(row) != (5 if media else 1) or not isinstance(row[0], str):
            raise ValueError("Unknown native vector identity")
        if media and row[1:] != [None, None, None, 1]:
            raise ValueError("Unmeasured image vector fields")
        ids.append(row[0])
    if len(ids) != len(set(ids)):
        raise ValueError("Native reference vector is not deduplicated")
    return tuple(ids)


def prompt_submit_problem(
    body: str, project: str, expected: tuple[NativePromptChunk, ...]
) -> str | None:
    """Verify exact literal/reference sequence and actual deduplicated attachments."""
    problem = "migrated host: positional image references could not be confirmed before submit"
    images = tuple(dict.fromkeys(chunk.value for chunk in expected if chunk.kind == "image"))
    entities = tuple(dict.fromkeys(chunk.value for chunk in expected if chunk.kind == "character"))
    try:
        for row in image_submit_rows(body, project):
            if (
                _chunks(row[8]) != expected
                or set(_vector(row[2], media=True)) != set(images)
                or set(_vector(row[10], media=False)) != set(entities)
            ):
                return problem
    except (ValueError, TypeError, KeyError, IndexError):
        return problem
    return None


@dataclass(frozen=True)
class NativeImageBinding:
    media_id: str
    name: str
    token: str = ""


async def remove_picker_space(page: Page) -> None:
    """Delete only the measured picker-added separator, never caller literal text."""
    # Local import keeps the composer's existing native upload imports acyclic.
    from gflow_cli.api.transports.migrated_composer import COMPOSER  # noqa: PLC0415

    verified = await page.locator(COMPOSER).first.evaluate(
        "e => { const s = window.getSelection(); const n = s?.anchorNode;"
        "return !!s && s.isCollapsed && !!n && e.contains(n)"
        "&& n.nodeType === Node.TEXT_NODE && n.textContent === ' '"
        "&& s.anchorOffset === 1; }"
    )
    if verified is not True:
        raise ValueError("Unmeasured native picker separator; prompt composition abandoned")
    await page.keyboard.press("Backspace")


async def materialize_reference_prompt(
    page: Page,
    composer: MigratedComposer,
    plan: ResolvedReferencePrompt,
    images: dict[str, NativeImageBinding],
    names: dict[str, str],
) -> tuple[NativePromptChunk, ...]:
    """Compose literal spans and identity-verified chips in their requested order.

    Caller binds logical source IDs to acknowledged uploaded IDs or grid tokens.
    Exact outgoing verification remains mandatory before Google's paid mutation.
    """
    if (
        plan.surface != "image"
        or set(images) != set(plan.image_ids)
        or set(names) != set(plan.character_ids)
    ):
        raise ValueError("Native image prompt attachments do not match the validated plan")
    if any(not binding.media_id for binding in images.values()) or any(
        not name for name in names.values()
    ):
        raise ValueError("Native image references require authoritative binding names")
    from gflow_cli.api.image import ImageRef  # noqa: PLC0415
    from gflow_cli.api.transports.migrated_composer import (  # noqa: PLC0415
        _picker_query,  # pyright: ignore[reportPrivateUsage]
    )

    unresolved = tuple(
        ImageRef(binding.media_id, display_name=binding.name, in_project=True)
        for binding in images.values()
        if not binding.token
        and (
            not binding.name
            or _picker_query(ImageRef(binding.media_id, display_name=binding.name)) != binding.name
        )
    )
    if unresolved:
        tokens = await composer.await_existing_references(page, unresolved)
        images = {
            key: replace(binding, token=tokens[binding.media_id])
            if binding.media_id in tokens
            else binding
            for key, binding in images.items()
        }
    mentioned = {span.identifier for span in plan.spans if isinstance(span, ReferenceMarker)}
    spans: list[ReferenceMarker | TextSpan] = []
    for identifier in (*plan.image_ids, *plan.character_ids):
        if identifier not in mentioned:
            kind: Literal["image", "character"] = "image" if identifier in images else "character"
            spans.extend([ReferenceMarker(0, 0, "", kind, identifier), TextSpan(0, 0, " ")])
    spans.extend(plan.spans)
    await composer.clear_composer(page)
    expected: list[NativePromptChunk] = []
    count = 0
    for span in spans:
        if isinstance(span, TextSpan):
            if span.text:
                await page.keyboard.insert_text(span.text)
                if expected and expected[-1].kind == "text":
                    previous = expected.pop()
                    expected.append(NativePromptChunk("text", previous.value + span.text))
                else:
                    expected.append(NativePromptChunk("text", span.text))
            continue
        count += 1
        if span.kind == "image":
            binding = images[span.identifier]
            if binding.token:
                await composer._mention_by_token(  # pyright: ignore[reportPrivateUsage]
                    page,
                    _picker_query(ImageRef(binding.media_id, display_name=binding.name)),
                    binding.token,
                    binding.media_id,
                    expect_chips=count,
                    at_end=True,
                    trailing_space=False,
                )
            else:
                await composer._mention_by_name(  # pyright: ignore[reportPrivateUsage]
                    page, binding.name, expect_chips=count, at_end=True, trailing_space=False
                )
            expected.append(NativePromptChunk("image", binding.media_id, binding.name))
        elif span.kind == "character":
            await composer._mention_by_name(  # pyright: ignore[reportPrivateUsage]
                page, names[span.identifier], expect_chips=count, at_end=True, trailing_space=False
            )
            expected.append(NativePromptChunk("character", span.identifier, names[span.identifier]))
        else:
            raise ValueError("Unmeasured native image reference kind")
        await remove_picker_space(page)
        chips = await composer.read_chips(page)
        expected_kind = "media" if span.kind == "image" else "entity"
        if len(chips) != count or chips[-1].get("reference_type") != expected_kind:
            raise ValueError("Native prompt committed a reference of the wrong kind")
        if span.kind == "character" and chips[-1].get("entity_id") != span.identifier:
            raise ValueError("Native prompt committed a different character identity")
    return tuple(expected)
