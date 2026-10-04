"""Read-only real checkpoint resume, fresh SDK calls, zero Google generation."""

import asyncio
import json
import os
import sqlite3

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.profile_store import read_account_file
from gflow_cli.services.inventory_sync import sync_native_inventory

scenarios("../features/native_inventory_sync_live.feature")


@given("an explicit private account for native inventory synchronization", target_fixture="case")
def configured(monkeypatch, tmp_path):
    if os.getenv("GFLOW_CLI_E2E_NATIVE_SYNC") != "1":
        pytest.skip("Explicit read-only native sync opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return {
        "root": tmp_path / "inventory",
        "profile": os.environ["GFLOW_CLI_E2E_PROFILE"],
        "generation": 0,
    }


@when("two bounded native sync calls share a private checkpoint")
def synchronize(case):
    async def run():
        settings = get_settings()
        account = read_account_file(settings.profile_subdir(case["profile"]))
        assert account is not None
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(case["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()

            async def guard(route):
                body = route.request.post_data or ""
                if any(
                    rpc in route.request.url or rpc in body
                    for rpc in (
                        "ogiZ0b",
                        "MZZa6b",
                        "fZytfe",
                        "jIps6",
                        "no0P6",
                        "YhhmEf",
                        "eb1hJf",
                        "p0UkFb",
                        "nprQif",
                    )
                ):
                    case["generation"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            client._checkin_page(page)
            case["first"] = await sync_native_inventory(
                client,
                case["root"],
                profile=case["profile"],
                account=account,
                max_steps=1,
                max_seconds=90,
            )
            with sqlite3.connect(case["root"] / "native_inventory_sync.sqlite3") as conn:
                case["version_before"] = conn.execute("SELECT version FROM checkpoints").fetchone()[
                    0
                ]
            case["second"] = await sync_native_inventory(
                client,
                case["root"],
                profile=case["profile"],
                account=account,
                max_steps=1,
                max_seconds=90,
            )
            with sqlite3.connect(case["root"] / "native_inventory_sync.sqlite3") as conn:
                case["version_after"] = conn.execute("SELECT version FROM checkpoints").fetchone()[
                    0
                ]
                case["metadata"] = [
                    json.loads(row[0]) for row in conn.execute("SELECT metadata FROM observations")
                ]
            page = await client._checkout_page()
            await page.unroute("**/batchexecute*", guard)
            client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 240))
    reset_settings()


@then("committed scope observations persist without Google generation")
def verified(case):
    assert case["first"]["steps_read"] == case["second"]["steps_read"] == 1
    assert case["version_after"] == case["version_before"] + 1
    assert case["second"]["catalog_projects_read"] == 1
    assert case["first"]["complete"] is case["second"]["complete"] is None
    assert case["metadata"]
    assert all(
        not set(row) & {"url", "audio_url", "prompt", "dialogue", "token"}
        for row in case["metadata"]
    )
    assert case["generation"] == 0
    print("native_sync_resume_steps", 2, "catalog_projects_read", 1, "generation", 0)
