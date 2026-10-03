"""One explicitly gated native metadata read; never generation."""

import asyncio
import math
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_video_edit import resolve_edit_window, source_video_duration
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/native_video_duration.feature")


@given("an explicitly configured duration metadata read", target_fixture="case")
def configured(monkeypatch):
    if os.environ.get("GFLOW_CLI_E2E_NATIVE_VIDEO_PATH") != "duration-metadata":
        pytest.skip("Explicit duration metadata read selection required")
    values = {
        key: os.environ.get("GFLOW_CLI_E2E_" + key)
        for key in ("PROFILE", "HOME", "RESOURCES_PROJECT")
    }
    if not all(values.values()):
        pytest.skip("Private profile/home/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    reset_settings()
    return values


@when("one owned native video snapshot is read")
def read(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            try:

                async def guard(route):
                    if any(
                        rpc in route.request.url
                        for rpc in ("ogiZ0b", "MZZa6b", "fZytfe", "jIps6", "no0P6")
                    ):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", guard)
                payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
                rows = parse_media_snapshot(payload, case["RESOURCES_PROJECT"])["media"]
                source = next(row for row in rows if row["kind"] == "video")
                duration = source_video_duration(
                    payload, case["RESOURCES_PROJECT"], source["media_id"]
                )
                case["duration"] = duration
                case["end"] = resolve_edit_window(duration, 0, None)
            finally:
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 90))


@then("its default virtual frame end is measured and bounded")
def bounded(case):
    assert math.isfinite(case["duration"]) and case["duration"] > 0
    assert case["end"] == min(math.floor(case["duration"] * 24), 240)
    assert 0 < case["end"] <= 240
