"""Opt-in fresh-owned exact-ID discovery; no upload, submit or solver."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import ImageRef
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_grid_discovery.feature")


@given("an explicitly configured no-submit native grid probe", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_GRID_DISCOVERY") != "native":
        pytest.skip("Explicit no-submit native grid discovery required")
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()):
        pytest.skip("Private authenticated profile/home/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    reset_settings()
    values["generation_requests"] = 0
    return values


@given("an explicitly selected older owned image in a large project")
def deep_reference(case):
    target = os.getenv("GFLOW_CLI_E2E_GRID_DEEP_MEDIA", "")
    if not target:
        pytest.skip("Explicit older owned image identity required")
    case["deep_target"] = target


@when("a fresh owned unmounted image is discovered in the current project")
def discover(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            try:

                async def guard(route):
                    request = route.request
                    if any(
                        rpc in request.url or rpc in (request.post_data or "")
                        for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6")
                    ):
                        case["generation_requests"] += 1
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
                owned = parse_media_snapshot(payload, case["RESOURCES_PROJECT"])["media"]
                timeline = project_media(payload, case["RESOURCES_PROJECT"])
                active = {
                    row["workflow_id"]
                    for row in timeline
                    if not row["archived"]
                    and sum(other["workflow_id"] == row["workflow_id"] for other in timeline) == 1
                }
                composer = MigratedComposer()
                await composer.ensure_editor(page, case["RESOURCES_PROJECT"])
                await page.wait_for_timeout(500)
                mounted = await page.locator("img[data-media-id]").evaluate_all(
                    "images=>images.map(e=>e.getAttribute('data-media-id'))"
                )
                target = next(
                    (
                        row["media_id"]
                        for row in owned
                        if row["kind"] == "image"
                        and row["media_id"] not in mounted
                        and (not case.get("deep_target") or row["media_id"] == case["deep_target"])
                        and row["workflow_id"] in active
                        and type(row.get("width")) is int
                        and row["width"] > 0
                        and type(row.get("height")) is int
                        and row["height"] > 0
                    ),
                    None,
                )
                if target is None and case.get("deep_target"):
                    pytest.fail("Selected older image must be fresh, active, owned and unmounted")
                if target is None:
                    pytest.skip("Current project has no owned image outside its mounted window")
                position = page.locator(".page-container.cdk-virtual-scrollable")
                assert await position.count() == 1
                before = await position.evaluate("e=>e.scrollTop")
                if case.get("deep_target"):
                    bounds = await position.evaluate(
                        "e=>({height:e.clientHeight,total:e.scrollHeight})"
                    )
                    assert bounds["total"] > bounds["height"] * 12 * 0.8
                    assert target == case["deep_target"]

                tokens = await composer.await_existing_references(page, (ImageRef(target),))
                case["resolved"] = bool(tokens.get(target))
                case["restored"] = abs(await position.evaluate("e=>e.scrollTop") - before) < 1
                case["state_clean"] = await page.evaluate(
                    "Object.keys(window).filter(k=>k.startsWith('__gflow_grid_')).length===0"
                )
            finally:
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 90))


@then("its exact token is resolved and grid position is restored without generation")
def verified(case):
    assert case["resolved"] is True
    assert case["restored"] is True
    assert case["state_clean"] is True
    assert case["generation_requests"] == 0


@when("a fresh owned repeated-caption image is hydrated and attached")
def attach_repeated(case):
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.native_image_references import validate_native_image_references
    from gflow_cli.api.transports.migrated_composer import _picker_query
    from gflow_cli.errors import ReferenceNotFoundError

    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            composer = MigratedComposer()
            try:

                async def guard(route):
                    request = route.request
                    if any(
                        rpc in request.url or rpc in (request.post_data or "")
                        for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6")
                    ):
                        case["generation_requests"] += 1
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
                timeline = project_media(payload, case["RESOURCES_PROJECT"])
                media = parse_media_snapshot(payload, case["RESOURCES_PROJECT"])["media"]
                candidates = []
                for row in media:
                    matches = [w for w in timeline if w["workflow_id"] == row["workflow_id"]]
                    if row["kind"] != "image" or len(matches) != 1 or matches[0]["archived"]:
                        continue
                    caption = matches[0].get("caption")
                    if not isinstance(caption, str):
                        continue
                    if sum(w.get("caption") == caption and not w["archived"] for w in timeline) < 2:
                        continue
                    ref = ImageRef(row["media_id"], display_name=caption)
                    try:
                        _picker_query(ref)
                    except ReferenceNotFoundError:
                        continue
                    candidates.append(ref)
                if not candidates:
                    pytest.skip("No active owned repeated-caption image with a safe picker query")
                target = candidates[0]
                # Fresh SDK validation owns its own page lease. Return this
                # discovery lease first; the default pool contains one page.
                client._checkin_page(page)
                page = None
                request = await validate_native_image_references(
                    client,
                    case["RESOURCES_PROJECT"],
                    GenerateImageRequest(prompt="No-submit attachment probe", refs=(target,)),
                )
                page = await client._checkout_page()
                await composer.ensure_editor(page, case["RESOURCES_PROJECT"])
                await composer.clear_composer(page)
                ids = await composer.reference_existing(page, case["RESOURCES_PROJECT"], request)
                case["attached"] = ids == (target.name,)
                chips = await composer.read_chips(page)
                case["media_chip"] = len(chips) == 1 and chips[0].get("reference_type") == "media"
            finally:
                # No submit button or generation method is invoked.
                if page is not None:
                    try:
                        if case.get("attached"):
                            await composer.clear_composer(page)
                    finally:
                        client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 120))


@then("its exact reference is attached without generation")
def attached_without_generation(case):
    assert case["attached"] is True
    assert case["media_chip"] is True
    assert case["generation_requests"] == 0


@when("the selected older owned image is hydrated and attached")
def attach_older(case):
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.api.native_image_references import validate_native_image_references

    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            composer = MigratedComposer()
            editor_ready = False
            try:

                async def guard(route):
                    request = route.request
                    if any(
                        rpc in request.url or rpc in (request.post_data or "")
                        for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6", "SPrCad")
                    ):
                        case["generation_requests"] += 1
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                client._checkin_page(page)
                page = None
                request = await validate_native_image_references(
                    client,
                    case["RESOURCES_PROJECT"],
                    GenerateImageRequest(
                        prompt="No-submit older image probe", refs=(ImageRef(case["deep_target"]),)
                    ),
                )
                assert request.refs[0].in_project
                page = await client._checkout_page()
                await composer.ensure_editor(page, case["RESOURCES_PROJECT"])
                await composer.clear_composer(page)
                editor_ready = True
                ids = await composer.reference_existing(page, case["RESOURCES_PROJECT"], request)
                case["attached"] = ids == (case["deep_target"],)
                chips = await composer.read_chips(page)
                case["media_chip"] = len(chips) == 1 and chips[0].get("reference_type") == "media"
            finally:
                if page is not None:
                    try:
                        if editor_ready:
                            await composer.clear_composer(page)
                    finally:
                        client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 120))
