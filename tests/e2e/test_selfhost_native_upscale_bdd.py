"""Native Flow image upscale BDD; existing image only, zero credits.

Opt-in: GFLOW_CLI_E2E_PROFILE, GFLOW_CLI_E2E_HOME,
GFLOW_CLI_E2E_UPSCALE_PROJECT, GFLOW_CLI_E2E_UPSCALE_MEDIA,
GFLOW_CLI_E2E_UPSCALE_SOURCE (local original image).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.errors import UpscaleUnavailableError

scenarios("../features/selfhost_native_upscale.feature")


@given("an authenticated Pro profile and an existing Flow image", target_fixture="upscale_case")
def upscale_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    keys = ("PROFILE", "HOME", "UPSCALE_PROJECT", "UPSCALE_MEDIA", "UPSCALE_SOURCE")
    values = {key: os.environ.get(f"GFLOW_CLI_E2E_{key}", "") for key in keys}
    if not all(values.values()):
        pytest.skip("Native upscale requires all documented GFLOW_CLI_E2E_* inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    values["out"] = str(tmp_path)
    values["result"] = ""
    return values


async def _client_upscale(case: dict[str, Any], resolution: TargetResolution) -> Path:
    profile_dir = get_settings().profile_subdir(case["PROFILE"])
    async with FlowApiClient(profile_dir=profile_dir, headless=False) as client:
        result = await client.upsample_image(
            project_id=case["UPSCALE_PROJECT"],
            media_id=case["UPSCALE_MEDIA"],
            target_resolution=resolution,
            out_path=Path(case["out"]) / "upscaled.jpg",
        )
    return Path(str(result))


@when("the shared client upscales the image to 2K")
def upscale_2k(upscale_case: dict[str, Any]) -> None:
    upscale_case["result"] = asyncio.run(_client_upscale(upscale_case, TargetResolution.RES_2K))


@when("the MCP image tool upscales the image to 2K")
def upscale_mcp(upscale_case: dict[str, Any]) -> None:
    from gflow_cli.mcp.tools import gflow_upscale_image

    result = asyncio.run(
        gflow_upscale_image(
            media_id=upscale_case["UPSCALE_MEDIA"],
            project=upscale_case["UPSCALE_PROJECT"],
            profile=upscale_case["PROFILE"],
            out_dir=upscale_case["out"],
            scale="2k",
        )
    )
    assert result["status"] == "ok", result
    upscale_case["result"] = Path(result["path"])


@then("the result is a valid image with doubled source dimensions")
def verify_2k(upscale_case: dict[str, Any]) -> None:
    with Image.open(upscale_case["UPSCALE_SOURCE"]) as original:
        expected = tuple(value * 2 for value in original.size)
    with Image.open(upscale_case["result"]) as output:
        assert output.size == expected
        output.verify()


@when("the shared client requests 4K")
def upscale_4k(upscale_case: dict[str, Any]) -> None:
    with pytest.raises(UpscaleUnavailableError):
        asyncio.run(_client_upscale(upscale_case, TargetResolution.RES_4K))


@then("the account tier refusal prevents producing an output file")
def verify_no_file(upscale_case: dict[str, Any]) -> None:
    assert not list(Path(upscale_case["out"]).glob("upscaled.*"))
