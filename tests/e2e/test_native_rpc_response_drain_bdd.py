"""Opt-in authoritative catalog read; no upload, generation or archive."""

import asyncio
import os
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_upload_drain import (
    MAX_PROJECT_RESPONSE_BYTES,
    UploadResponseDrain,
)
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_rpc_response_drain.feature")


@given("an explicit authenticated read-only project", target_fixture="case")
def configured(monkeypatch):
    values = {
        key: os.getenv("GFLOW_CLI_E2E_" + key, "")
        for key in ("HOME", "PROFILE", "RESOURCES_PROJECT")
    }
    if not all(values.values()):
        pytest.skip("Explicit private authenticated profile/project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    assert Path(values["HOME"]).is_dir()
    case = {**values, "observations": []}
    original = UploadResponseDrain.result

    async def record(drain):
        observation = await original(drain)
        if drain.rpc == "Zzl0ze":
            case["observations"].append(observation)
        return observation

    monkeypatch.setattr(UploadResponseDrain, "result", record)
    return case


@when("the SDK reads its authoritative project timeline once")
def read_once(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            try:
                payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
                case["media"] = project_media(payload, case["RESOURCES_PROJECT"])
            finally:
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 60))


@then("its scoped catalog stream reaches clean EOF and the canonical payload validates")
def verified(case):
    assert isinstance(case["media"], list)
    assert len(case["observations"]) == 1
    observation = case["observations"][0]
    assert observation.observed is True
    assert observation.matches == 1
    assert observation.complete is True
    assert observation.limit == MAX_PROJECT_RESPONSE_BYTES
    assert 0 < observation.bytes <= MAX_PROJECT_RESPONSE_BYTES
    assert observation.allows_ack is True
