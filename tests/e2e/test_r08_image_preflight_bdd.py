"""R08 original-profile preflight; all generation boundaries replaced by local stops."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest, ImageRef, Model
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_image_references import validate_native_image_references
from gflow_cli.api.reference_markers import prepare_ordered_image_slots
from gflow_cli.api.transports.migrated_catalog import parse_native_characters
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.errors import ConfigurationError

scenarios("../features/r08_image_preflight.feature")


class PreflightStopError(Exception):
    pass


@given("an original profile explicitly selected for R08 read only checks", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_R08_READONLY") != "1":
        pytest.skip("Explicit R08 read-only opt-in required")
    profile = os.environ["GFLOW_CLI_E2E_PROFILE"]
    assert profile in {"pro2", "pro3"}
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {
        "profile": profile,
        "project": os.environ["GFLOW_CLI_E2E_RESOURCES_PROJECT"],
        "prepared": 0,
        "forbidden": 0,
        "character_checks": 0,
    }


@when("its existing images and characters pass current image request preparation")
def preflight(case, monkeypatch):
    async def run():
        project = case["project"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:

            async def forbidden(*args, **kwargs):
                case["forbidden"] += 1
                pytest.fail("R08 attempted upload or mint")

            monkeypatch.setattr(client, "upload_reference", forbidden)
            monkeypatch.setattr(client, "_mint_recaptcha_token", forbidden)
            models = await client.list_native_image_reference_models(project)
            case["capacities"] = {
                row["model_key"]: [row["effective_reference_cap"], row["effective_character_cap"]]
                for row in models
            }
            page = await client._checkout_page()
            try:
                snapshot = await read_project_payload(page, project)
            finally:
                client._checkin_page(page)
            media = parse_media_snapshot(snapshot, project)["media"]
            timeline = project_media(snapshot, project)
            active = {row["workflow_id"] for row in timeline if not row["archived"]}
            ids = list(
                dict.fromkeys(
                    row["media_id"]
                    for row in media
                    if row["workflow_id"] in active
                    and row["kind"] == "image"
                    and all(type(row.get(k)) is int and row[k] > 0 for k in ("width", "height"))
                )
            )[:10]
            assert len(ids) == 10, "Ten existing active decoded-dimension images required"
            refs = tuple(ImageRef(identifier) for identifier in ids)

            async def stop(*args, **kwargs):
                req = kwargs["request"]
                assert tuple(ref.name for ref in req.refs) == tuple(ids)
                assert req.reference_prompt_plan.image_ids == tuple(ids)
                assert (req.count, req.seed, req.aspect) == (2, 42, Aspect.PORTRAIT_THREE_FOUR)
                assert all(ref.in_project for ref in req.refs)
                case["prepared"] += 1
                raise PreflightStopError

            monkeypatch.setattr(client.transport, "generate_images", stop)
            for key in ("NARWHAL", "GEM_PIX_2", "HARBOR_SEAL"):
                assert case["capacities"][key][0] == 10
                req = prepare_ordered_image_slots(
                    GenerateImageRequest(
                        prompt="@reference_10 then @reference_1 then @reference_10",
                        model=Model(key),
                        refs=refs,
                        count=2,
                        seed=42,
                        aspect=Aspect.PORTRAIT_THREE_FOUR,
                        reference_syntax="slots",
                    )
                )
                with pytest.raises(PreflightStopError):
                    await client._drive_images_generation(
                        project_id=project, req=req, recaptcha_action="IMAGE_GENERATION"
                    )
                with pytest.raises(ValueError):
                    replace(req, refs=(*refs, ImageRef(str(uuid4()))))
            with pytest.raises(ConfigurationError):
                await validate_native_image_references(
                    client,
                    project,
                    GenerateImageRequest(
                        prompt="Missing reference", refs=(ImageRef(str(uuid4())),)
                    ),
                )
            aspect, decision = await client.resolve_native_image_aspect(project, ids[0])
            assert aspect is Aspect.from_cli(decision.resolved_aspect)
            case["auto_policy"] = decision.policy
            characters = parse_native_characters(snapshot, project)
            for character in characters:
                weight = len(character["workflow_ids"])
                if weight not in {1, 2}:
                    continue
                req = GenerateImageRequest(
                    prompt="@reference_1 @character_1",
                    refs=refs[: 10 - weight],
                    reference_entities=(character["entity_id"],),
                    reference_syntax="slots",
                )
                try:
                    checked = await validate_native_image_references(
                        client, project, prepare_ordered_image_slots(req)
                    )
                except ConfigurationError:
                    continue  # Unusable existing characters are not substituted or modified.
                assert (
                    next(
                        s.image_count
                        for s in checked.reference_prompt_plan.slots
                        if s.kind == "character"
                    )
                    == weight
                )
                with pytest.raises((ConfigurationError, ValueError)):
                    await validate_native_image_references(
                        client, project, replace(req, refs=refs[: 11 - weight])
                    )
                case["character_checks"] += 1
                case["character_weight"] = weight
                break

    asyncio.run(run())


@then("no upload mint solver or generation operation has occurred")
def verified(case):
    assert case["forbidden"] == 0 and case["prepared"] == 3
    print("R08_READONLY", {k: v for k, v in case.items() if k != "project"})
