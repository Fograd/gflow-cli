"""Abort-only canonical ten-image wire proof; no generation allowance consumed."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest, ImageRef, Model
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request
from gflow_cli.api.transports.image_entity_grounding import image_submit_rows
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.native_image_prompt import _chunks, _vector
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_ten_retention.feature")


class CapturedBeforeDispatchError(Exception):
    pass


@given("a selected real image model and ten owned native references", target_fixture="case")
def configured(monkeypatch, tmp_path):
    if os.getenv("GFLOW_CLI_E2E_TEN_RETAIN") != "1":
        pytest.skip("Explicit abort-only ten-reference opt-in required")
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {
        "profile": os.environ["GFLOW_CLI_E2E_PROFILE"],
        "project": os.environ["GFLOW_CLI_E2E_RESOURCES_PROJECT"],
        "model": os.environ["GFLOW_CLI_E2E_TEN_MODEL"],
        "captured": 0,
        "dispatch": 0,
        "fixture_root": tmp_path / "ten-fixtures",
        "uploaded": [],
    }


@when("its canonical request is intercepted and aborted before Google generation")
def retain(case):
    async def run():
        project = case["project"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()
            payload = await read_project_payload(page, project)
            active = {
                row["media_id"] for row in project_media(payload, project) if not row["archived"]
            }
            selected = list(
                dict.fromkeys(
                    row["media_id"]
                    for row in parse_media_snapshot(payload, project)["media"]
                    if row["kind"] == "image" and row["media_id"] in active
                )
            )[:10]
            case["originals"] = active
            fixture_path = os.getenv("GFLOW_CLI_E2E_TEN_INPUT_FIXTURE")
            if fixture_path:
                fixture = json.loads(Path(fixture_path).read_text())
                assert fixture["project"] == project
                selected = fixture["ids"]
                assert len(selected) == 10 and len(set(selected)) == 10
                assert set(selected) <= active, "Fresh active ownership required"
                case["uploaded"] = list(selected)
                case["originals"] = active - set(selected)
            if os.getenv("GFLOW_CLI_E2E_TEN_UPLOAD_FIXTURE") == "1":
                client._checkin_page(page)
                page = None
                selected = []
                case["fixture_root"].mkdir()
                prefix = "tenfixture" + uuid4().hex[:8]
                for index in range(10):
                    path = case["fixture_root"] / (prefix + str(index) + ".png")
                    Image.new("RGB", (256, 256), (index * 20, 40, 180)).save(path)
                    asset = await client.upload_reference(project, path)
                    case["uploaded"].append(asset.name)
                    selected.append(asset.name)
                page = await client._checkout_page()
                for _ in range(12):
                    fresh = await read_project_payload(page, project)
                    visible = {
                        row["media_id"]
                        for row in project_media(fresh, project)
                        if not row["archived"]
                    }
                    if set(selected) <= visible:
                        break
                    await asyncio.sleep(2)
                assert set(selected) <= visible, "Uploaded fixtures not yet visible"
            assert len(selected) == 10, "Ten verified active owned image inputs required"

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
                    case["dispatch"] += 1
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/batchexecute*", guard)
            client._checkin_page(page)
            page = None
            request = GenerateImageRequest(
                prompt=" ".join("@reference_" + str(i) for i in range(1, 11))
                + " A balanced composition.",
                model=Model(case["model"]),
                count=1,
                refs=tuple(ImageRef(mid) for mid in selected),
            )
            request = prepare_image_slot_request(
                request,
                {
                    f"reference_{i}": ReferenceSlot("image", mid)
                    for i, mid in enumerate(selected, 1)
                },
            )

            async def capture(page, body):
                case["captured"] += 1
                assert case["captured"] == 1, "No intercepted-submit replay"
                rows = image_submit_rows(body, project)
                assert len(rows) == 1 and case["model"] in body
                row = rows[0]
                assert set(_vector(row[2], media=True)) == set(selected)
                assert [
                    chunk.value for chunk in _chunks(row[8]) if chunk.kind == "image"
                ] == selected
                case["identities"] = 10
                raise CapturedBeforeDispatchError

            override = ImageOverrides(project, 1, metadata_required=False)
            override.apply = capture
            scope = active_overrides.set(override)
            try:
                try:
                    await client.generate_images_batch(project_id=project, req=request, count=1)
                except Exception as error:
                    case["stop_class"] = type(error).__name__
                    case["stop_detail"] = str(error)
            finally:
                active_overrides.reset(scope)
                if page is None:
                    page = await client._checkout_page()
                if case["uploaded"]:
                    try:
                        assert (
                            await trash_media(page, project, case["uploaded"]) == case["uploaded"]
                        )
                        remaining = await read_project_payload(page, project)
                        assert case["originals"] <= {
                            row["media_id"]
                            for row in project_media(remaining, project)
                            if not row["archived"]
                        }
                    except Exception as error:
                        case["cleanup_error"] = type(error).__name__
                        if case["captured"]:
                            raise
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 420))
    reset_settings()


@then("all ten exact references and their prompt order survive without dispatch")
def verified(case):
    assert case["captured"] == 1, (case.get("stop_class"), case.get("stop_detail"))
    assert case["identities"] == 10
    assert case["dispatch"] == 0
    print("retained_native_images", 10, "model", case["model"], "google_dispatch", 0)
