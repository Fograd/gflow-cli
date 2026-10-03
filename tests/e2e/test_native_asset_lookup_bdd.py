"""Zero-generation native GetMedia/content proof; explicit opt-in account/project."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/native_asset_lookup.feature")


@given("an explicitly selected logged-in native asset project", target_fixture="case")
def configured(monkeypatch, tmp_path):
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT")
    values = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_ASSET_LOOKUP") != "1":
        pytest.skip("Explicit native asset lookup profile/project opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "directory": tmp_path, "writes": [], "results": []}


@when("fresh image and video metadata and content are retrieved")
def retrieve(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            assert client._context is not None

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
                        "cz8Z4b",
                        "lt8g5",
                        "mYWVGd",
                    )
                ):
                    case["writes"].append(True)
                    await route.abort()
                else:
                    await route.continue_()

            await client._context.route("**/batchexecute*", guard)
            try:
                project = case["RESOURCES_PROJECT"]
                snapshot = await client.list_native_media(project)
                for kind in ("image", "video"):
                    selected = next((row for row in snapshot["media"] if row["kind"] == kind), None)
                    assert selected is not None, "Representative owned type unavailable"
                    result = await client.download_native_asset(
                        project, selected["media_id"], case["directory"]
                    )
                    assert (result.media_id, result.project_id, result.workflow_id) == (
                        selected["media_id"],
                        project,
                        selected["workflow_id"],
                    )
                    assert (result.width, result.height) == (selected["width"], selected["height"])
                    case["results"].append(result)
            finally:
                await client._context.unroute("**/batchexecute*", guard)

    asyncio.run(asyncio.wait_for(perform(), 240))


@then("content matches the owned media and no resource write was requested")
def verified(case):
    assert [result.kind for result in case["results"]] == ["image", "video"]
    assert not case["writes"]
    for result in case["results"]:
        assert result.path.is_file() and result.path.stat().st_size == result.bytes > 0
        assert len(result.sha256) == 64
