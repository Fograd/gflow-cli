"""Opt-in real SDK catalog resume; fresh reads guarded against generation."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_catalog_resume.feature")


@given("an explicit authenticated native account for catalog resume", target_fixture="case")
def configured(monkeypatch):
    values = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in ("PROFILE", "HOME")}
    if os.getenv("GFLOW_CLI_E2E_CATALOG_RESUME") != "1" or not all(values.values()):
        pytest.skip("Explicit read-only native catalog resume opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "generation_requests": 0, "catalogs_returned": 0, "complete": None}


@when("a capped project inventory is resumed using one pending project identity")
def resume(case):
    async def run():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                request = route.request
                if any(
                    rpc in request.url or rpc in (request.post_data or "")
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "YhhmEf",
                        "eb1hJf",
                        "p0UkFb",
                    )
                ):
                    case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            client._checkin_page(page)
            try:
                first = await client.list_native_projects(include_catalogs=True, max_projects=1)
                pending = first.get("pending_project_ids", [])
                if not pending:
                    pytest.skip(
                        "At least two discovered owned projects are required for catalog resume"
                    )
                selected = pending[0]
                second = await client.list_native_projects(
                    include_catalogs=True, max_projects=1, catalog_project_ids=[selected]
                )
                catalogs = second.get("project_catalogs", [])
                if len(catalogs) != 1 or catalogs[0].get("project_id") != selected:
                    pytest.fail("Explicit pending project catalog was not returned", pytrace=False)
                if selected in second.get("pending_project_ids", []):
                    pytest.fail(
                        "Read project must no longer be pending in the current snapshot",
                        pytrace=False,
                    )
                case["catalogs_returned"] = len(catalogs)
                case["complete"] = catalogs[0].get("complete")
            finally:
                await page.unroute("**/batchexecute*", guard)

    asyncio.run(run())


@then("the fresh selected catalog is returned with unknown completeness and zero generation")
def checked(case):
    assert case["catalogs_returned"] == 1
    assert case["complete"] is None
    assert case["generation_requests"] == 0
