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
                        and row["workflow_id"] in active
                        and type(row.get("width")) is int
                        and row["width"] > 0
                        and type(row.get("height")) is int
                        and row["height"] > 0
                    ),
                    None,
                )
                if target is None:
                    pytest.skip("Current project has no owned image outside its mounted window")
                position = page.locator(".page-container.cdk-virtual-scrollable")
                assert await position.count() == 1
                before = await position.evaluate("e=>e.scrollTop")
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
