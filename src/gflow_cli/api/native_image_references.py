"""Fresh native ownership and weighted image budget before a billed submit."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from gflow_cli.api.image import GenerateImageRequest, ImageRef, reference_cap_for
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import ConfigurationError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


def _uuid(value: str) -> str:
    if not is_uuid(value):
        raise ConfigurationError(detail="Native image reference identifiers must be UUIDs")
    return str(UUID(value))


def _measured_inner_image_arm(candidate: object) -> bool:
    """Positive native image forms measured in 13 private snapshot rows.

    Two dimensionless rows had a 17-field first image payload. Other observed
    first payloads have 15 fields; the alternative arm has null first payload
    and a seven-field second payload. This is not a generic array classifier.
    """
    if not isinstance(candidate, list):
        return False
    row = cast(list[Any], candidate)
    if len(row) < 8 or row[7] is not None or not isinstance(row[6], list):
        return False
    arm = cast(list[Any], row[6])
    if not arm:
        return False
    first: Any = arm[0]
    if isinstance(first, list):
        return len(cast(list[Any], first)) in (15, 17)
    return (
        first is None
        and len(arm) > 1
        and isinstance(arm[1], list)
        and len(cast(list[Any], arm[1])) == 7
    )


def _hydrate_owned_images(
    refs: tuple[ImageRef, ...],
    media: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    by_image: dict[str, str],
) -> tuple[ImageRef, ...]:
    """Hydrate only identities already proven active/exclusive in this snapshot."""
    hydrated: list[ImageRef] = []
    for ref in refs:
        identifier = str(UUID(ref.name))
        if sum(str(UUID(row["media_id"])) == identifier for row in media) != 1:
            raise ValueError("Ambiguous native image identity")
        workflow = by_image[identifier]
        matches = [row for row in timeline if str(UUID(row["workflow_id"])) == workflow]
        if len(matches) != 1:
            raise ValueError("Ambiguous native image workflow")
        caption = matches[0].get("caption")
        if caption is None:
            caption = ""
        elif not isinstance(caption, str):
            raise ValueError("Native image caption has an invalid type")
        # Captions are search labels, not identities. The migrated picker matches
        # this owned media UUID's exact grid token; the submit guard checks its ID.
        hydrated.append(replace(ref, display_name=caption, in_project=True))
    return tuple(hydrated)


async def validate_native_image_references(
    client: FlowApiClient, project_id: str, request: GenerateImageRequest
) -> GenerateImageRequest:
    """Validate all entities against one authoritative same-project snapshot.

    Names are taken from the current catalog, never trusted as ownership proof.
    A two-image entity consumes two image budget slots. Unknown or ambiguous
    workflow kinds fail closed, before any token mint or submit checkpoint.
    """
    project_id = _uuid(project_id)
    entities = tuple(dict.fromkeys(_uuid(value) for value in request.reference_entities))
    image_ids = tuple(dict.fromkeys(_uuid(ref.name) for ref in request.refs))
    try:
        local_paths = tuple(dict.fromkeys(path.resolve() for path in request.ref_paths))
    except (OSError, RuntimeError):
        raise ConfigurationError(
            detail="Local image reference paths could not be resolved"
        ) from None
    if local_paths:
        from gflow_cli.api.image_aspect_policy import derive_aspect_from_file

        try:
            for path in local_paths:
                derive_aspect_from_file(path)
        except ValueError as exc:
            raise ConfigurationError(
                detail="Local image references must be bounded decoded PNG or JPEG files"
            ) from exc
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        payload = await read_project_payload(page, project_id)
        characters = parse_native_characters(payload, project_id)
        media = parse_media_snapshot(payload, project_id)["media"]
        timeline = project_media(payload, project_id)
        owned = {str(UUID(row["entity_id"])): row for row in characters}
        if len(owned) != len(characters):
            raise ValueError("Duplicate native character identity")
        states: dict[str, list[bool]] = {}
        for row in timeline:
            if row["project_id"] != project_id:
                raise ValueError("Unrelated native timeline")
            states.setdefault(str(UUID(row["workflow_id"])), []).append(row["archived"])
        active = {workflow for workflow, values in states.items() if values == [False]}
        measured_inner = {str(UUID(row[0])): _measured_inner_image_arm(row) for row in payload[2]}
        by_workflow: dict[str, list[str]] = {}
        decoded_images: dict[str, list[bool]] = {}
        by_image: dict[str, str] = {}
        for row in media:
            if row["project_id"] != project_id:
                raise ValueError("Unrelated native media")
            workflow = str(UUID(row["workflow_id"]))
            by_workflow.setdefault(workflow, []).append(row["kind"])
            positive_image = row["kind"] == "image" and (
                all(
                    type(row.get(field)) is int and 0 < row[field] <= 100000
                    for field in ("width", "height")
                )
                or measured_inner.get(str(UUID(row["media_id"])), False)
            )
            decoded_images.setdefault(workflow, []).append(positive_image)
            if positive_image and workflow in active:
                by_image[str(UUID(row["media_id"]))] = workflow
        if any(
            image_id not in by_image
            or set(by_workflow[by_image[image_id]]) != {"image"}
            or not all(decoded_images[by_image[image_id]])
            for image_id in image_ids
        ):
            raise ValueError("Unknown or inactive image reference")
        names: list[str] = []
        verified_counts: dict[str, int] = {}
        # Each supplied local path is uploaded separately by the current transport.
        # Decode aliases once, but budget actual upload inputs rather than undercounting.
        total = len(image_ids) + len(request.ref_paths)
        for entity in entities:
            row = owned.get(entity)
            if row is None or row["project_id"] != project_id:
                raise ValueError("Unknown or unrelated character")
            workflows = [_uuid(value) for value in row["workflow_ids"]]
            if not 1 <= len(workflows) <= 2 or len(set(workflows)) != len(workflows):
                raise ValueError("Unknown character reference image count")
            if any(
                workflow not in active
                or not by_workflow.get(workflow)
                or set(by_workflow[workflow]) != {"image"}
                or not all(decoded_images[workflow])
                for workflow in workflows
            ):
                raise ValueError("Character references nonimage or inactive workflow")
            name = row["display_name"]
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                raise ValueError("Native character name unavailable")
            names.append(name)
            verified_counts[entity] = len(workflows)
            total += len(workflows)
        cap = reference_cap_for(request.model)
        if total > cap:
            raise ConfigurationError(
                detail=f"Native image reference budget exceeded; model allows {cap} image slots"
            )
        hydrated_refs = _hydrate_owned_images(request.refs, media, timeline, by_image)
        plan = request.reference_prompt_plan
        if plan is not None:
            from gflow_cli.api.reference_markers import (
                ReferenceContractError,
                validate_reference_budget,
            )

            if plan.character_ids != entities:
                raise ConfigurationError(
                    detail="Reference plan does not match verified character inputs"
                )
            plan = replace(
                plan,
                slots=tuple(
                    replace(slot, image_count=verified_counts[slot.identifier])
                    if slot.kind == "character"
                    else slot
                    for slot in plan.slots
                ),
            )
            canonical = {
                "NARWHAL": "nano-banana-2",
                "GEM_PIX_2": "nano-banana-pro",
                "HARBOR_SEAL": "nano-banana-2-lite",
            }.get(request.model.name)
            if canonical is None:
                raise ConfigurationError(detail="Native slot mode requires a measured image model")
            try:
                validate_reference_budget(
                    plan, surface="image", model=canonical, native_image_cap=cap
                )
            except ReferenceContractError as exc:
                raise ConfigurationError(detail=str(exc)) from exc
        return replace(
            request,
            refs=hydrated_refs,
            reference_entities=entities,
            reference_entity_names=tuple(names),
            reference_prompt_plan=plan,
        )
    except ValueError as exc:
        raise ConfigurationError(
            detail="Native reference ownership or image count could not be verified"
        ) from exc
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
