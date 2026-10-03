"""Read-only native audio eligibility against a fresh project."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_video_edit import validate_edit_audio
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.errors import ConfigurationError

scenarios("../features/native_edit_audio.feature")


@given(
    "an explicit native profile and project for read-only edit audio preflight",
    target_fixture="case",
)
def configured(monkeypatch):
    profile = os.getenv("GFLOW_CLI_E2E_PROFILE", "")
    home = os.getenv("GFLOW_CLI_E2E_HOME", "")
    project = os.getenv("GFLOW_CLI_E2E_PROJECT", "")
    if not profile or not home or not project:
        pytest.skip("Explicit private profile/home/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", home)
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"profile": profile, "project": project, "generation_requests": 0}


@when("the fresh project payload is checked for exclusive active owned audio")
def preflight(case):
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
                payload = await read_project_payload(page, case["project"])
                nonaudio = [
                    row[0]
                    for row in payload[2]
                    if len(row) > 7 and (row[6] is not None or row[7] is not None)
                ]
                if not nonaudio:
                    pytest.skip("Owned non-audio fixture required")
                with pytest.raises(ConfigurationError):
                    validate_edit_audio(payload, case["project"], (nonaudio[0],))
                case["non_audio_refused"] = True
                case["accepted_audio_count"] = 0
                for row in payload[2]:
                    if len(row) > 10 and row[10] is not None:
                        try:
                            validate_edit_audio(payload, case["project"], (row[0],))
                        except ConfigurationError:
                            continue
                        case["accepted_audio_count"] += 1
            finally:
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 90))


@then("non-audio is refused and only owned audio passes without generation")
def verified(case):
    assert case["non_audio_refused"]
    assert case["generation_requests"] == 0
