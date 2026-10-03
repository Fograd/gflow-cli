"""Opt-in one synthetic upload, canonical attachment and archive; never generate."""

import asyncio
import os
from pathlib import Path

import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.reference_markers import ReferenceSlot, resolve_reference_markers
from gflow_cli.api.transports import migrated_composer
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.native_image_prompt import (
    NativeImageBinding,
    materialize_reference_prompt,
)
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_upload_binding.feature")


@given("an explicit one-upload no-generation allowance", target_fixture="case")
def configured(monkeypatch, tmp_path):
    keys = ("PROFILE", "HOME", "RESOURCES_PROJECT", "IMAGE_UPLOAD_ALLOWANCE")
    values = {key: os.getenv("GFLOW_CLI_E2E_" + key, "") for key in keys}
    if not all(values.values()):
        pytest.skip("Explicit private profile/project and one-upload allowance required")
    allowance = Path(values["IMAGE_UPLOAD_ALLOWANCE"])
    if allowance.exists():
        pytest.skip("This one-upload allowance has already been consumed")
    allowance.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GFLOW_CLI_HOME", values["HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    reset_settings()
    unsafe_caption = os.getenv("GFLOW_CLI_E2E_UPLOAD_UNSAFE_CAPTION") == "1"
    path = tmp_path / ("unsafe@reference\ncaption.png" if unsafe_caption else "synthetic-owned.png")
    Image.new("RGB", (48, 32), (25, 85, 145)).save(path)
    case = {**values, "path": path, "generation_requests": 0, "unsafe_caption": unsafe_caption}
    unique_name = migrated_composer._unique_display_name

    def capture_name(image_path):
        caption = unique_name(image_path)
        case["caption"] = caption
        return caption

    monkeypatch.setattr(migrated_composer, "_unique_display_name", capture_name)
    evidence = os.getenv("GFLOW_CLI_E2E_UPLOAD_ACK_EVIDENCE", "")
    if evidence:
        decoder = migrated_composer._uploaded_image_id

        def capture_ack(text, project, caption=None):
            target = Path(evidence)
            with target.open("x") as stream:
                stream.write(text)
            target.chmod(0o600)
            return decoder(text, project, caption)

        monkeypatch.setattr(migrated_composer, "_uploaded_image_id", capture_ack)
    return case


@when("the toolbar uploads a synthetic image and binds its canonical slot")
def upload_and_bind(case):
    async def perform():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["PROFILE"]), headless=False
        ) as client:
            page = await client._checkout_page()
            composer = MigratedComposer()
            media_id = None
            try:

                async def guard(route):
                    request = route.request
                    if any(
                        rpc in request.url or rpc in (request.post_data or "")
                        for rpc in (
                            "ogiZ0b",
                            "MZZa6b",
                            "fZytfe",
                            "jIps6",
                            "no0P6",
                            "YhhmEf",
                            "eb1hJf",
                        )
                    ):
                        case["generation_requests"] += 1
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                project = case["RESOURCES_PROJECT"]
                await composer.ensure_editor(page, project)
                await composer.clear_composer(page)
                with Path(case["IMAGE_UPLOAD_ALLOWANCE"]).open("x") as allowance:
                    allowance.write("one synthetic toolbar upload; never replay\n")
                media_id, caption = await composer._upload_via_toolbar(page, project, case["path"])
                if case["unsafe_caption"]:
                    assert "@" in caption and "\n" in caption
                for _ in range(12):
                    payload = await read_project_payload(page, project)
                    media = parse_media_snapshot(payload, project)["media"]
                    timeline = project_media(payload, project)
                    rows = [row for row in media if row["media_id"] == media_id]
                    workflows = [
                        row
                        for row in timeline
                        if len(rows) == 1 and row["workflow_id"] == rows[0]["workflow_id"]
                    ]
                    if (
                        len(rows) == 1
                        and rows[0]["kind"] == "image"
                        and len(workflows) == 1
                        and not workflows[0]["archived"]
                        and workflows[0].get("caption") == caption
                    ):
                        case["owned"] = True
                        break
                    await asyncio.sleep(0.5)
                assert case.get("owned") is True
                plan = resolve_reference_markers(
                    "Use @reference_1.",
                    surface="image",
                    slots={"reference_1": ReferenceSlot("image", "local-reference-1")},
                )
                chunks = await materialize_reference_prompt(
                    page,
                    composer,
                    plan,
                    {"local-reference-1": NativeImageBinding(media_id, caption)},
                    {},
                )
                case["binding"] = any(
                    chunk.kind == "image" and chunk.value == media_id for chunk in chunks
                )
                chips = await composer.read_chips(page)
                case["chip"] = len(chips) == 1 and chips[0].get("reference_type") == "media"
            finally:
                try:
                    await composer.clear_composer(page)
                    if not media_id and case.get("caption"):
                        # A 200 response can represent a completed upload even if
                        # its current shape is unknown. Recover only this run's
                        # exact unique caption with one fresh typed identity.
                        payload = await read_project_payload(page, case["RESOURCES_PROJECT"])
                        rows = parse_media_snapshot(payload, case["RESOURCES_PROJECT"])["media"]
                        workflows = [
                            row
                            for row in project_media(payload, case["RESOURCES_PROJECT"])
                            if not row["archived"] and row.get("caption") == case["caption"]
                        ]
                        recovered = [
                            row
                            for row in rows
                            if len(workflows) == 1
                            and row["workflow_id"] == workflows[0]["workflow_id"]
                            and row["kind"] == "image"
                        ]
                        if len(recovered) == 1:
                            media_id = recovered[0]["media_id"]
                    if media_id:
                        case["archived"] = await trash_media(
                            page, case["RESOURCES_PROJECT"], [media_id]
                        ) == [media_id]
                finally:
                    client._checkin_page(page)

    asyncio.run(asyncio.wait_for(perform(), 150))


@then("the exact owned image is attached and archived without generation")
def verified(case):
    assert case["owned"] is True
    assert case["binding"] is True
    assert case["chip"] is True
    assert case["archived"] is True
    assert case["generation_requests"] == 0
