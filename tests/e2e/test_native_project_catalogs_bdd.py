"""Opt-in account catalog projection against one fresh native project."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_project_catalogs.feature")


@given(
    "an explicit native account profile for read-only catalog aggregation", target_fixture="case"
)
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    if not profile or not home:
        pytest.skip("Explicit private profile/home required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"profile": profile, "generation_requests": 0}


@when("native project listing includes catalogs for at most one project")
def catalogs(case):
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
            case["snapshot"] = await client.list_native_projects(
                include_catalogs=True, max_projects=1
            )

    asyncio.run(asyncio.wait_for(perform(), 210))


@then("owned typed catalogs and unread discovered project IDs are returned without generation")
def verified(case):
    result = case["snapshot"]
    assert result["catalog_projects_read"] == len(result["project_catalogs"]) == 1
    catalog = result["project_catalogs"][0]
    assert catalog["complete"] is None and result["complete"] is None
    for field in ("media", "workflows", "characters", "user_voices"):
        assert catalog["counts"][field] == len(catalog[field]) == result["catalog_counts"][field]
        assert all(row["project_id"] == catalog["project_id"] for row in catalog[field])
        assert not any(key.endswith("url") for row in catalog[field] for key in row)
    assert result["pending_project_ids"] == [row["project_id"] for row in result["projects"][1:]]
    assert result["catalogs_capped"] == bool(result["pending_project_ids"])
    assert case["generation_requests"] == 0
