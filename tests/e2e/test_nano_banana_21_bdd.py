"""Opt-in live catalogue and picker proof; no generation or solver call."""

import asyncio
import os

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest, Model
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/nano_banana_21.feature")


@given("an explicitly configured native Flow account for Nano Banana 2.1", target_fixture="case")
def configured(monkeypatch):
    case = {
        key: os.getenv("GFLOW_CLI_E2E_" + key) for key in ("HOME", "PROFILE", "RESOURCES_PROJECT")
    }
    if not all(case.values()):
        pytest.skip("Explicit E2E home, profile and project required")
    monkeypatch.setenv("GFLOW_CLI_HOME", case["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return case


@when("Gflow reads its live image models and selects Nano Banana 2.1")
def select(case):
    async def run():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            case["models"] = await client.list_native_image_reference_models(
                case["RESOURCES_PROJECT"]
            )
            page = await client._checkout_page()
            try:
                composer = MigratedComposer()
                await composer.ensure_editor(page, case["RESOURCES_PROJECT"])
                await composer.apply_image_settings(
                    page,
                    GenerateImageRequest(
                        prompt="Read-only model selection",
                        model=Model.from_cli("nano2.1"),
                        aspect=Aspect.SQUARE,
                        count=1,
                    ),
                )
                case["selected"] = True
            finally:
                client._checkin_page(page)

    asyncio.run(run())


@then("BELUGA is advertised and its settings are applied without generation")
def verify(case):
    rows = [row for row in case["models"] if row["model_key"] == "BELUGA"]
    assert len(rows) == 1
    assert "2.1" in rows[0]["display_name"]
    assert 1 <= rows[0]["effective_reference_cap"] <= 10
    assert case["selected"] is True
