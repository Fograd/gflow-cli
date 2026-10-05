"""Actual original-profile health reads, no generation, cookie transfer or solver."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.selfhost.session_health import probe_project_access

scenarios("../features/r10_session_health_live.feature")


@given("an explicit original profile for R10 read-only health verification", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_R10_HEALTH") != "1":
        pytest.skip("Explicit R10 read-only health opt-in required")
    profile = os.environ["GFLOW_CLI_E2E_PROFILE"]
    assert profile in {"pro2", "pro3"}
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return {"profile": profile, "project": os.environ["GFLOW_CLI_E2E_PROJECT"], "results": []}


@when("health probing cold opens that profile twice")
def cold_checks(case):
    async def run():
        for _ in range(2):
            case["results"].append(await probe_project_access(case["profile"], case["project"]))

    try:
        asyncio.run(asyncio.wait_for(run(), 240))
    finally:
        reset_settings()


@then("both checks verify current identity and native project access without renewal")
def verify(case):
    for observation in case["results"]:
        assert observation["health"] == "OK" and observation["reason"] == "project_access_verified"
        assert observation.get("identityVerified") is True
        assert observation["profilePreserved"] is True
        assert observation["refreshAttempted"] is False
