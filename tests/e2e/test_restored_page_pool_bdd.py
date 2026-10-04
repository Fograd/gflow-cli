"""Read-only real Flow session reuse and bounded restored tabs; zero generation."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.auth.native_identity import read_native_identity
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.profile_store import read_account_file

scenarios("../features/restored_page_pool_live.feature")


@given("an explicit authenticated profile for restored page pool checks", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_PAGE_POOL_REUSE") != "1":
        pytest.skip("Explicit read-only page pool opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "2")
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    profile = get_settings().profile_subdir(os.environ["GFLOW_CLI_E2E_PROFILE"])
    account = read_account_file(profile)
    assert account is not None
    return {"profile": profile, "account": account, "observations": []}


@when("the Flow client cold opens that profile twice")
def cold_open(case):
    async def run():
        for _ in range(2):
            async with FlowApiClient(profile_dir=case["profile"], headless=False) as client:
                assert client._context is not None
                assert client._page is not None
                principal = await read_native_identity(client._page)
                case["observations"].append(
                    (len(client._context.pages), principal.casefold() == case["account"].casefold())
                )

    try:
        asyncio.run(asyncio.wait_for(run(), 180))
    finally:
        reset_settings()


@then("both opens keep exactly the configured page pool and the current account")
def verified(case):
    assert case["observations"] == [(2, True), (2, True)]
