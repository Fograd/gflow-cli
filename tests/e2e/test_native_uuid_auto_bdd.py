"""Opt-in read-only native sizing proof; no uploads or billed generation."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.services import image_aspect
from gflow_cli.services.image_aspect import aspect_decision_metadata

scenarios("../features/native_uuid_auto.feature")


@given(
    "an authenticated profile and an existing owned image for Auto sizing", target_fixture="case"
)
def sizing_case(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT", "CHARACTER_FIRST_MEDIA")
    case = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(case.values()):
        pytest.skip("Read-only native Auto requires explicitly owned E2E inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", case["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Sizing must not invoke generation")

    derive = image_aspect.derive_aspect

    def measured(width: int, height: int):
        case["dimensions"] = (width, height)
        return derive(width, height)

    monkeypatch.setattr(image_aspect, "derive_aspect", measured)
    monkeypatch.setattr(FlowApiClient, "generate_image", forbidden)
    return case


@when("the SDK resolves Auto from the native image metadata")
def resolve(case: dict[str, Any]) -> None:
    async def run() -> dict[str, str]:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            _, decision = await client.resolve_native_image_aspect(
                case["RESOURCES_PROJECT"], case["CHARACTER_FIRST_MEDIA"]
            )
            return aspect_decision_metadata(decision)

    case["result"] = asyncio.run(run())


@then("the ratio uses the documented policy and no generation is requested")
def verified(case: dict[str, Any]) -> None:
    width, height = case["dimensions"]
    assert width > 0 and height > 0
    print(
        f"NATIVE_AUTO_READ width={width} height={height} "
        f"ratio={case['result']['resolvedAspectRatio']}"
    )
    assert case["result"]["requestedAspectRatio"] == "auto"
    assert case["result"]["resolvedAspectRatio"] in {"16:9", "9:16", "1:1", "4:3", "3:4"}
    assert case["result"]["aspectPolicy"] == "derived-first-reference-nearest-supported-v1"
