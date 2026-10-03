"""Opt-in free real Patchright native model read; no generation acceptance claim."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_page_context.feature")


@given(
    "an explicit Patchright native profile and project for a read-only context check",
    target_fixture="case",
)
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    project = os.getenv("GFLOW_CLI_E2E_PROJECT", "")
    if not profile or not home or not project:
        pytest.skip("Explicit private profile/home/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", "patchright")
    reset_settings()
    return {"profile": profile, "project": project, "write_requests": 0}


@when("the SDK reads fresh native video edit models")
def model_read(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                if any(
                    rpc in route.request.url or rpc in (route.request.post_data or "")
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "p0UkFb",
                        "YhhmEf",
                        "eb1hJf",
                        "cz8Z4b",
                        "pGCYOe",
                        "lt8g5",
                        "mYWVGd",
                    )
                ):
                    case["write_requests"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            try:
                await page.route("**/batchexecute*", guard)
            finally:
                client._checkin_page(page)
            case["models"] = await client.list_native_video_edit_models(case["project"])

    asyncio.run(asyncio.wait_for(perform(), 90))


@then("available native model metadata is returned without mutation or generation")
def verified(case):
    assert case["models"]
    assert all(isinstance(row, dict) and row.get("model_key") for row in case["models"])
    assert case["write_requests"] == 0
