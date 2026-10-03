"""Opt-in free character reference detail proof; creates/removes only its fixture."""

import asyncio
import os
import uuid

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.character_details import lookup_character
from gflow_cli.api.transports.migrated_characters import mutate_character
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/character_detail_urls.feature")


@given("an explicitly selected logged in character detail project", target_fixture="case")
def configured(monkeypatch):
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT")
    values = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_CHARACTER_DETAIL") != "1":
        pytest.skip("Explicit character detail profile/project opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "writes": [], "verified": False, "cleaned": False}


@when("one free copied image character is read with fresh detail URLs")
def perform(case):
    async def run():
        project = case["RESOURCES_PROJECT"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            created = None

            async def guard(route):
                if any(
                    rpc in route.request.url or rpc in (route.request.post_data or "")
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "YhhmEf",
                        "eb1hJf",
                        "maseQ",
                        "pGCYOe",
                    )
                ):
                    case["writes"].append(True)
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            try:
                before = parse_media_snapshot(await read_project_payload(page, project), project)[
                    "media"
                ]
                source = next(row for row in before if row["kind"] == "image")
                try:
                    result = await mutate_character(
                        page,
                        project,
                        "create",
                        name="detail-bdd-" + uuid.uuid4().hex[:12],
                        source_media_id=source["media_id"],
                        image_reference_confirmed=True,
                    )
                    created = result["character"]["entity_id"]
                except BaseException as error:
                    created = getattr(error, "entity_id", "") or None
                    raise
                detail = await lookup_character(page, project_id=project, entity_id=created)
                assert detail["entity_id"] == created and detail["project_id"] == project
                refs = detail["image_references"]
                assert len(refs) == 1
                assert refs[0]["preview_url"].startswith("https://flow-content.google/image/")
                assert detail["thumbnail_media_id"] == refs[0]["media_id"]
                assert detail["thumbnail_url"] == refs[0]["preview_url"]
                case["verified"] = True
            finally:
                try:
                    if created:
                        await mutate_character(page, project, "delete", entity_id=created)
                        after = parse_media_snapshot(
                            await read_project_payload(page, project), project
                        )["media"]
                        assert {r["media_id"] for r in before} <= {r["media_id"] for r in after}
                        case["cleaned"] = True
                finally:
                    await page.unroute("**/batchexecute*", guard)
                    client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 180))
    reset_settings()


@then("the thumbnail matches the owned reference and the fixture is removed without generation")
def verified(case):
    assert case["verified"] and case["cleaned"]
    assert not case["writes"]
