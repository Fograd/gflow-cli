"""Opt-in read-only native cursor traversal; no generation."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_project_traversal.feature")


@given("an explicit native account profile for read-only project traversal", target_fixture="case")
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    if not profile or not home:
        pytest.skip("Explicit private native profile/home required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"profile": profile, "generation_requests": 0}


@when("the native inventory traverses at most two project pages")
def traverse(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                if any(
                    rpc in route.request.url or rpc in (route.request.post_data or "")
                    for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6", "YhhmEf", "eb1hJf")
                ):
                    case["generation_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            try:
                await page.route("**/batchexecute*", guard)
            finally:
                client._checkin_page(page)
            case["snapshot"] = await client.list_native_projects(all_pages=True, max_pages=2)

    asyncio.run(asyncio.wait_for(perform(), 210))


@then("unique project identities and honest continuation are returned without generation")
def verify(case):
    result = case["snapshot"]
    assert result["pages_read"] == 2
    ids = [row["project_id"].lower() for row in result["projects"]]
    assert len(ids) == len(set(ids)) == result["returned_count"]
    assert result["complete"] is None
    assert result["pagination_exhausted"] == (result["next_cursor"] is None)
    assert case["generation_requests"] == 0
