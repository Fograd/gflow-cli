"""Opt-in free native reads: no mutations, generation or fixture assets."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_sdk_inventory.feature")


@given("an authenticated profile and an owned existing image project", target_fixture="inventory")
def inventory(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT", "CHARACTER_FIRST_MEDIA")
    values = {key: os.environ.get("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()):
        pytest.skip("Native SDK inventory requires documented owned E2E inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    return values


async def _read(case: dict[str, Any]) -> dict[str, Any]:
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        first = await client.list_native_projects()
        ids = {row["project_id"] for row in first["projects"]}
        assert len(ids) == first["returned_count"]
        assert first["next_cursor"]
        assert first["returned_count"] == 21 and first["complete"] is None
        second = await client.list_native_projects(first["next_cursor"])
        assert second["returned_count"] == 21 and second["complete"] is None
        assert ids.isdisjoint({row["project_id"] for row in second["projects"]})
        media = await client.list_native_media(case["RESOURCES_PROJECT"])
        rows = [row for row in media["media"] if row["media_id"] == case["CHARACTER_FIRST_MEDIA"]]
        assert len(rows) == 1 and rows[0]["kind"] == "image"
        assert rows[0].get("width", 0) > 0 and rows[0].get("height", 0) > 0
        assert len({row["media_id"] for row in media["media"]}) == media["returned_count"]
        assert media["complete"] is None
        assert all(
            set(row) <= {"media_id", "project_id", "workflow_id", "kind", "width", "height"}
            for row in media["media"]
        )
        return {
            "returned_count": media["returned_count"],
            "known_image": True,
            "complete": media["complete"],
        }


@when("the native SDK reads account project pages and project media")
def read_inventory(inventory: dict[str, Any]) -> None:
    inventory["result"] = asyncio.run(_read(inventory))


@then("returned identities are distinct and the image kind is observed without signed URLs")
def verify_inventory(inventory: dict[str, Any]) -> None:
    assert inventory["result"]["known_image"]
    assert inventory["result"]["complete"] is None
