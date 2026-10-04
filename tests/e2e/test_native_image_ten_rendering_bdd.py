"""Explicit one-image ten-reference acceptance; persistent marker prevents replay."""

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
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.api.transports.migrated_image_overrides import ImageOverrides, active_overrides
from gflow_cli.api.transports.migrated_resources import (
    project_media,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.native_image_prompt import _chunks, _vector
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_image_ten_rendering.feature")


@given("a selected real image model and ten owned native references", target_fixture="case")
def configured(monkeypatch, tmp_path):
    if os.getenv("GFLOW_CLI_E2E_TEN_RENDER") != "1":
        pytest.skip("Explicit one-image ten-reference rendering allowance required")
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    output = Path(os.environ["GFLOW_CLI_E2E_TEN_OUTPUT"])
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    descriptor = os.open(output / "invocation.marker", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    return {
        "output": output,
        "profile": os.environ["GFLOW_CLI_E2E_PROFILE"],
        "project": os.environ["GFLOW_CLI_E2E_RESOURCES_PROJECT"],
        "model": os.environ["GFLOW_CLI_E2E_TEN_MODEL"],
        "captured": 0,
        "dispatch": 0,
        "fixture_root": tmp_path / "ten-fixtures",
        "uploaded": [],
    }


@when("its validated canonical request is submitted exactly once")
def retain(case, monkeypatch):
    original_clear = MigratedComposer.clear_composer
    original_mention = MigratedComposer._mention_by_token

    async def measured_clear(composer, page):
        before = len(await composer.read_chips(page))
        await original_clear(composer, page)
        after = len(await composer.read_chips(page))
        case.setdefault("clear_counts", []).append([before, after])

    async def measured_mention(composer, page, *args, **kwargs):
        try:
            return await original_mention(composer, page, *args, **kwargs)
        except Exception:
            chips = await composer.read_chips(page)
            case["attachment_failure"] = {
                "expected_chips": kwargs.get("expect_chips"),
                "observed_chips": len(chips),
                "types": [chip.get("reference_type") for chip in chips],
            }
            raise

    monkeypatch.setattr(MigratedComposer, "clear_composer", measured_clear)
    monkeypatch.setattr(MigratedComposer, "_mention_by_token", measured_mention)

    async def run():
        project = case["project"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(case["profile"]), headless=False
        ) as client:
            page = None
            guard = None
            try:
                models = await client.list_native_image_reference_models(project)
                selected_model = [row for row in models if row["model_key"] == case["model"]]
                assert len(selected_model) == 1
                assert selected_model[0]["effective_reference_cap"] >= 10
                page = await client._checkout_page()
                payload = await read_project_payload(page, project)
                active = {
                    row["media_id"]
                    for row in project_media(payload, project)
                    if not row["archived"]
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
                        rows = image_submit_rows(body, project)
                        if case["captured"] == 1 and case["dispatch"] == 0 and len(rows) == 1:
                            # The composer's validated route normally bypasses this guard.
                            # An unexpected direct generation route must not dispatch.
                            case["blocked_dispatch"] = case.get("blocked_dispatch", 0) + 1
                            await route.abort()
                        else:
                            case["blocked_dispatch"] = case.get("blocked_dispatch", 0) + 1
                            await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/batchexecute*", guard)
                client._checkin_page(page)
                page = None
                request = GenerateImageRequest(
                    prompt=" ".join("@reference_" + str(i) for i in range(1, 11))
                    + " Create one wide collage inspired by the colors of all these "
                    "reference images.",
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
                    return await original_apply(page, body)

                def submitted(phase):
                    if phase == "submitted":
                        case["dispatch"] += 1
                        assert case["dispatch"] == 1, "No native image replay"

                override = ImageOverrides(project, 1, metadata_required=False, observe=submitted)
                original_apply = override.apply
                override.apply = capture
                scope = active_overrides.set(override)
                try:
                    try:
                        images = await client.generate_images_batch(
                            project_id=project, req=request, count=1
                        )
                        assert len(images) == 1
                        result = images[0]
                        case["output_media"] = result.media_name
                        path = case["output"] / "image.png"
                        path = Path(await client.download_image(result, path))
                        assert path.resolve().is_relative_to(case["output"].resolve())
                        path.chmod(0o600)
                        with Image.open(path) as decoded:
                            decoded.load()
                            case["dimensions"] = list(decoded.size)
                            assert min(decoded.size) >= 256
                        read_page = await client._checkout_page()
                        try:
                            fresh = await read_project_payload(read_page, project)
                        finally:
                            client._checkin_page(read_page)
                        case["output_owned"] = result.media_name in {
                            row["media_id"]
                            for row in project_media(fresh, project)
                            if not row["archived"]
                        }
                        assert case["output_owned"]
                        case["accepted_outputs"] = 1
                    except Exception as error:
                        case["stop_class"] = type(error).__name__
                        case["stop_detail"] = str(error)
                finally:
                    active_overrides.reset(scope)
            finally:
                if page is None and (case["uploaded"] or guard is not None):
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
                if guard is not None:
                    await page.unroute("**/batchexecute*", guard)
                if page is not None:
                    client._checkin_page(page)

    try:
        asyncio.run(asyncio.wait_for(run(), 600))
    finally:
        reset_settings()
        proof = {
            key: value
            for key, value in case.items()
            if key
            in {
                "captured",
                "dispatch",
                "blocked_dispatch",
                "identities",
                "accepted_outputs",
                "dimensions",
                "output_owned",
                "cleanup_error",
                "stop_class",
                "model",
                "output_media",
                "uploaded",
                "clear_counts",
                "attachment_failure",
            }
        }
        descriptor = os.open(
            case["output"] / "proof.private.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump(proof, stream)


@then("all ten ordered references produce one decoded owned image")
def verified(case):
    assert case["captured"] == 1, (case.get("stop_class"), case.get("stop_detail"))
    assert case["identities"] == 10
    assert case["dispatch"] == 1
    assert case.get("accepted_outputs") == 1, case.get("stop_class")
    assert case["output_owned"]
    assert case.get("blocked_dispatch", 0) == 0
    assert "cleanup_error" not in case
    print("native_inputs", 10, "decoded_outputs", 1, "google_dispatch", 1)
