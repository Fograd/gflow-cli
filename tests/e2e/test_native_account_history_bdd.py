"""Opt-in free actual SDK history traversal; no paid or completeness claims."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_account_history.feature")


@given(
    "an explicit private native account profile with at least forty observed workflows",
    target_fixture="case",
)
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    if not profile or not home:
        pytest.skip("Explicit private native profile/home required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"profile": profile, "write_requests": 0, "history_responses": []}


@when("the SDK reads two native history pages with a forty-media bound")
def read_history(case):
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
                        "rzMKMb",
                        "C4BZMd",
                        "Sc7aEb",
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
            # Inspect only validated URL-free parser output at the read boundary.
            import gflow_cli.api.native_history as module

            original = module.parse_history_page

            def observe(payload):
                parsed = original(payload)
                case["history_responses"].append(parsed)
                return parsed

            # Scoped observation does not alter page evaluate or RPC requests.
            from unittest.mock import patch

            with patch.object(module, "parse_history_page", observe):
                case["snapshot"] = await client.list_native_history(
                    all_pages=True, max_pages=2, max_media=40
                )

    asyncio.run(asyncio.wait_for(perform(), 60))


@then("two disjoint owned pages are returned without private fields or writes")
def verified(case):
    result = case["snapshot"]
    pages = case["history_responses"]
    assert result["pages_read"] == len(pages) == 2
    assert result["returned_count"] == len(result["workflows"]) == 40
    assert result["media_returned_count"] == len(result["media"]) == 40
    assert result["complete"] is None and result["timed_out"] is False
    assert pages[0]["next_cursor"] and pages[0]["next_cursor"] != pages[1]["next_cursor"]
    assert result["next_cursor"] == pages[1]["next_cursor"]
    assert result["pagination_exhausted"] == (result["next_cursor"] is None)
    first = {row["workflow_id"] for row in pages[0]["workflows"]}
    second = {row["workflow_id"] for row in pages[1]["workflows"]}
    assert not first & second
    assert not (
        {row["media_id"] for row in pages[0]["media"]}
        & {row["media_id"] for row in pages[1]["media"]}
    )
    owners = {row["workflow_id"]: row["project_id"] for row in result["workflows"]}
    for row in result["media"]:
        assert owners[row["workflow_id"]] == row["project_id"]
        assert set(row) <= {"media_id", "project_id", "workflow_id", "kind", "width", "height"}
    assert all(
        set(row) <= {"workflow_id", "project_id", "primary_media_id"} for row in result["workflows"]
    )
    assert case["write_requests"] == 0
