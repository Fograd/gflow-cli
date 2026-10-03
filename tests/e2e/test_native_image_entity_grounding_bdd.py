"""Opt-in ONE native image submit; download failures never trigger a new generation."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import Aspect, GenerateImageRequest, ImageRef
from gflow_cli.api.image_aspect_policy import derive_aspect_from_file
from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request
from gflow_cli.api.transports.image_entity_grounding import entity_submit_problem
from gflow_cli.api.transports.migrated_characters import CharacterBindingError, mutate_character
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_entity_grounding.feature")


@given(
    "an authenticated profile and existing owned image references for native grounding",
    target_fixture="grounding",
)
def grounding(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    keys = (
        "PROFILE",
        "HOME",
        "RESOURCES_PROJECT",
        "CHARACTER_FIRST_MEDIA",
        "GROUNDING_MEDIA",
        "GROUNDING_FILE",
        "GROUNDING_OUTPUT",
    )
    values = {key: os.environ.get("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()) or os.environ.get("GFLOW_CLI_E2E_RUN_GROUNDING") != "1":
        pytest.skip("Native grounding requires explicit one-image permission and owned inputs")
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_FLOW_HOST", "flow.google.com")
    monkeypatch.delenv("GFLOW_CLI_DB_PATH", raising=False)
    reset_settings()
    return values


async def _exercise(case: dict[str, Any]) -> dict[str, Any]:
    project = case["RESOURCES_PROJECT"]
    decision = derive_aspect_from_file(Path(case["GROUNDING_FILE"]))
    output = Path(case["GROUNDING_OUTPUT"])
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    entity, attempts = "", 0
    name = "grounding-proof-" + uuid4().hex[:10]
    async with FlowApiClient(
        profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
    ) as client:
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]

        async def guard(route: Any) -> None:
            request = route.request
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                await route.continue_()
                return
            location = urlsplit(request.url)
            if location.hostname == "flow.google.com" and "batchexecute" in location.path:
                try:
                    wrappers = json.loads(parse_qs(request.post_data or "")["f.req"][0])
                    ids = {row[0] for group in wrappers for row in group}
                    allowed = {
                        "UpteDb",
                        "Zzl0ze",
                        "tRARke",
                        "as29s",
                        "ngNC2",
                        "o30O0e",
                        "KV2T2d",
                        "HTrJv",
                        "nzlxg",
                        "Yizz8d",
                        "ve2Lsc",
                        "yBhWQ",
                        "NfrxTb",
                        "cPZSdc",
                        "qJcgMc",
                        "LPzVkd",
                        "mrlkwd",
                        "GN0Bre",
                        "xI9TVb",
                        "C4BZMd",
                        "Sc7aEb",
                        "cz8Z4b",
                        "rzMKMb",
                    }
                    if ids <= allowed:
                        await route.continue_()
                        return
                except (ValueError, KeyError, TypeError, AssertionError):
                    pass
            elif location.hostname in {"www.google.com", "www.recaptcha.net"} and location.path in {
                "/recaptcha/enterprise/reload",
                "/recaptcha/enterprise/clr",
                "/recaptcha/enterprise/userverify",
            }:
                await route.continue_()
                return
            await route.abort()

        await page.route("**/*", guard)
        try:
            payload = await read_project_payload(page, project)
            source = next(
                row
                for row in project_media(payload, project)
                if row["media_id"] == case["GROUNDING_MEDIA"] and not row["archived"]
            )
            created = await mutate_character(
                page,
                project,
                "create",
                name=name,
                source_media_id=case["CHARACTER_FIRST_MEDIA"],
                image_reference_confirmed=True,
            )
            entity = created["character"]["entity_id"]
            assert len(created["character"]["workflow_ids"]) == 1
            request = GenerateImageRequest(
                prompt="Draw @reference_1 beside @character_1 and @reference_1.",
                aspect=Aspect.from_cli(decision.resolved_aspect),
                count=1,
                refs=(
                    ImageRef(source["media_id"], display_name=source["caption"], in_project=True),
                ),
                reference_entities=(entity,),
                reference_entity_names=(name,),
            )

            request = prepare_image_slot_request(
                request,
                {
                    "reference_1": ReferenceSlot("image", source["media_id"]),
                    "character_1": ReferenceSlot("character", entity, 1),
                },
            )

            async def authorize_once(page: Any, body: str) -> str:
                nonlocal attempts
                wrappers = json.loads(parse_qs(body)["f.req"][0])
                args = json.loads(wrappers[0][0][1])
                assert attempts == 0, "The one-image allowance cannot be replayed"
                assert len(args[1]) == 1, "Only one output is authorized"
                assert args[1][0][4] == 1, "Measured square scalar expected"
                assert entity_submit_problem(body, project, (entity,), (name,)) is None
                attempts += 1
                return body

            # The newest production route continues directly, so the scoped hook,
            # after all production guards, owns the one-submit counter.
            override = ImageOverrides(project, 1, metadata_required=False)
            override.apply = authorize_once
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
            page = None
            token = active_overrides.set(override)
            try:
                images = await client.generate_images_batch(
                    project_id=project, req=request, count=1
                )
            finally:
                active_overrides.reset(token)
            assert len(images) == 1
            checkpoint = output / "remote-checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "media": images[0].media_name,
                        "workflow": images[0].workflow_id,
                        "requestedAspectRatio": decision.requested_aspect,
                        "resolvedAspectRatio": decision.resolved_aspect,
                        "aspectPolicy": decision.policy,
                    }
                )
            )
            checkpoint.chmod(0o600)
            downloaded = await client.download_image(images[0], output / "native-grounding.jpg")
            with Image.open(downloaded) as image:
                image.load()
                assert image.width >= 1024 and image.height >= 1024
            return {"attempts": attempts, "decoded": True, "policy": decision.policy}
        except CharacterBindingError as exc:
            entity = exc.entity_id
            raise
        finally:
            if page is None:
                page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
            try:
                if entity:
                    await mutate_character(page, project, "delete", entity)
            finally:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


@when("one native image request carries verified character and image chunks")
def exercise(grounding: dict[str, Any]) -> None:
    grounding["result"] = asyncio.run(_exercise(grounding))


@then("one generated image is decoded and the owned character is cleaned up")
def verify(grounding: dict[str, Any]) -> None:
    assert grounding["result"]["attempts"] == 1
    assert grounding["result"]["decoded"]
