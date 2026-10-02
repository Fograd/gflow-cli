"""Live override proof using a fresh legitimate same-page token; no solver fee."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api._engine import mint_evaluate_kwargs
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/selfhost_captcha.feature")


@given("a verified Flow profile for image token testing", target_fixture="case")
def case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    required = {
        name: os.environ.get("GFLOW_CLI_E2E_" + name, "") for name in ("HOME", "PROFILE", "PROJECT")
    }
    if not all(required.values()):
        pytest.skip("Verified profile/project environment required")
    monkeypatch.setenv("GFLOW_CLI_HOME", required["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    return {**required, "out": tmp_path}


class ObservedOverride(ImageOverrides):
    original_hash: str = ""
    replacement_hash: str = ""

    async def apply(self, page: Any, body: str) -> str:
        args = json.loads(json.loads(parse_qs(body)["f.req"][0])[0][0][1])
        self.original_hash = hashlib.sha256(args[3][10][0].encode()).hexdigest()
        rewritten = await super().apply(page, body)
        args = json.loads(json.loads(parse_qs(rewritten)["f.req"][0])[0][0][1])
        self.replacement_hash = hashlib.sha256(args[3][10][0].encode()).hexdigest()
        return rewritten


async def run(case: dict[str, Any]) -> None:
    async def fresh(page: Any) -> str:
        metadata: Any = override.metadata
        assert isinstance(metadata, dict), "CAPTCHA metadata absent"
        data = cast(dict[str, Any], metadata)
        assert data.get("sitekey") and data.get("action")
        case["metadata_observed"] = True
        return await TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs()).mint(
            data["action"]
        )

    override = ObservedOverride(project=case["PROJECT"], count=1, token=fresh)
    state = active_overrides.set(override)
    try:
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]),
            headless=False,
            out_dir=case["out"],
        ) as client:
            image = await client.generate_image(
                project_id=case["PROJECT"],
                req=GenerateImageRequest(
                    prompt="A green ceramic sphere on a white background, studio photograph",
                    aspect=Aspect.SQUARE,
                    count=1,
                ),
            )
            case["media"] = image.media_name
    finally:
        active_overrides.reset(state)
    case["used"] = override.used
    case["changed"] = override.original_hash != override.replacement_hash


@when("a fresh same-page token overrides the native image request")
def generate(case: dict[str, Any]) -> None:
    asyncio.run(run(case))


@then("Google accepts the overridden request and returns an image")
def verify(case: dict[str, Any]) -> None:
    assert case["metadata_observed"] and case["used"] and case["changed"] and case["media"]
