"""Read-only generated-video proof with explicit existing account/project/media."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/native_generated_video_lookup.feature")


@given("an explicitly selected existing generated video", target_fixture="case")
def configured(monkeypatch, tmp_path):
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT", "GENERATED_VIDEO_MEDIA")
    values = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()) or os.getenv("GFLOW_CLI_E2E_GENERATED_VIDEO_LOOKUP") != "1":
        pytest.skip("Explicit existing generated-video opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {**values, "directory": tmp_path, "writes": []}


@when("its fresh URL and MP4 are retrieved without generation")
def retrieve(case):
    async def run():
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
            project, media = case["RESOURCES_PROJECT"], case["GENERATED_VIDEO_MEDIA"]
            asset = await client.get_native_asset(project, media)
            assert asset.kind == "video" and (asset.width, asset.height) == (None, None)
            case["asset"] = asset
            case["downloaded"] = await client.download_native_asset(
                project, media, case["directory"]
            )

    asyncio.run(asyncio.wait_for(run(), 180))


@then("missing metadata dimensions remain unknown and downloaded dimensions are measured")
def verified(case):
    asset, result = case["asset"], case["downloaded"]
    assert not case["writes"]
    assert (result.media_id, result.project_id, result.workflow_id) == (
        asset.media_id,
        asset.project_id,
        asset.workflow_id,
    )
    assert result.mime_type == "video/mp4" and result.width > 0 and result.height > 0
    assert result.path.stat().st_size == result.bytes > 0
    assert len(result.sha256) == 64
