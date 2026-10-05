"""Opt-in R12 live metadata and abort-before-forwarding frame contract proof."""

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import unquote_plus
from uuid import UUID

import pytest
from pytest_bdd import given, scenario, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.batchexecute import generation_record
from gflow_cli.api.transports.migrated_composer import (
    MIGRATED_PROJECT_URL,
    _body_rpcid,
    _interpolation_body_problem,
    _ligature,
    _prepare_native_video,
)
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel
from gflow_cli.config import get_settings, reset_settings


@pytest.mark.e2e_auth
@scenario(
    "../features/r12_measured_video_records.feature",
    "Current completed video metadata preserves exact owned identities",
)
def test_current_owned_video_record():
    pass


@pytest.mark.e2e_auth
@scenario(
    "../features/r12_measured_video_records.feature",
    "Fast first and last frames use the measured interpolation key",
)
def test_current_fast_frame_request():
    pass


def configured(prefix, monkeypatch):
    profile = os.environ.get(prefix + "_PROFILE")
    project = os.environ.get(prefix + "_PROJECT")
    if not profile or not project:
        pytest.skip("Private original-profile R12 contract fixture is not configured")
    assert profile in ("pro2", "pro3")
    original_home = os.environ.get("GFLOW_CLI_E2E_HOME")
    if not original_home:
        pytest.skip("Explicit original-profile home is required")
    monkeypatch.setenv("GFLOW_CLI_HOME", original_home)
    reset_settings()
    assert get_settings().profile_subdir(profile).is_dir()
    return {"profile": profile, "project": str(UUID(project))}


@given("an explicitly configured original-profile video evidence fixture", target_fixture="owned")
def owned_fixture(monkeypatch):
    value = configured("GFLOW_CLI_E2E_R12_RECORD", monkeypatch)
    value["media"] = str(UUID(os.environ["GFLOW_CLI_E2E_R12_RECORD_MEDIA"]))
    value["workflow"] = str(UUID(os.environ["GFLOW_CLI_E2E_R12_RECORD_WORKFLOW"]))
    return value


@when("the owned completed video metadata is read")
def read_metadata(owned):
    async def run():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(owned["profile"]), headless=False
        ) as client:
            # This read does not submit a generation or select an upscale.
            asset = await client.get_native_asset(
                project_id=owned["project"], media_id=owned["media"]
            )
            page = await client._checkout_page()
            try:
                await page.goto(
                    MIGRATED_PROJECT_URL.format(project_id=owned["project"]),
                    wait_until="domcontentloaded",
                )
                payload = await native_rpc(
                    page,
                    "as29s",
                    [owned["media"]],
                    "/project/" + owned["project"],
                    require_single=True,
                )
                owned["record"] = generation_record("as29s", payload)
                owned["asset"] = asset
                from gflow_cli.api.native_video_upscale import read_promotion_source

                owned["measured"] = await read_promotion_source(
                    page, project_id=owned["project"], media_id=owned["media"]
                )
            finally:
                client._checkin_page(page)

    asyncio.run(run())


@then("its generation record preserves the media project and workflow identities")
def verify_record(owned):
    record = owned["record"]
    assert (record.media_id, record.project_id, record.workflow_id) == (
        owned["media"],
        owned["project"],
        owned["workflow"],
    )
    assert record.is_done and record.video_url
    assert owned["asset"].workflow_id == record.workflow_id
    assert (owned["measured"].width, owned["measured"].height) == (1280, 720)


@given("an explicitly configured original-profile frame fixture", target_fixture="frames")
def frames_fixture(monkeypatch):
    value = configured("GFLOW_CLI_E2E_R12_FRAMES", monkeypatch)
    value["start"] = Path(os.environ["GFLOW_CLI_E2E_R12_FRAMES_START"])
    value["end"] = Path(os.environ["GFLOW_CLI_E2E_R12_FRAMES_END"])
    value["evidence"] = Path(os.environ["GFLOW_CLI_E2E_R12_FRAMES_EVIDENCE"])
    value["requests"] = []
    return value


@when("the two-output frame request is intercepted and aborted")
def intercepted_frames(frames):
    async def run():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(frames["profile"]), headless=False
        ) as client:
            page = await client._checkout_page()
            observed = asyncio.get_running_loop().create_future()

            async def guard(route):
                body = route.request.post_data or ""
                rpc = _body_rpcid(unquote_plus(body))
                if rpc not in ("YhhmEf", "eb1hJf", "nprQif", "MZZa6b"):
                    await route.fallback()
                    return
                # Fulfil locally, instead of depending on the engine's abort API.
                await route.fulfill(
                    status=409, content_type="application/json", body='{"r12":"not forwarded"}'
                )
                frames["requests"].append(rpc)
                frames["problem"] = _interpolation_body_problem(
                    unquote_plus(body), rpc, frames["bound"][0], frames["bound"][1]
                )
                frames["aborted"] = True
                if not observed.done():
                    observed.set_result(None)

            try:
                composer, _, start, end, _ = await _prepare_native_video(
                    page,
                    GenerateVideoRequest(
                        prompt="The same clay rabbit beside its mug, with a carrot arriving.",
                        mode=Mode.I2V,
                        model=VideoModel.VEO_3_1_FAST,
                        aspect=Aspect.LANDSCAPE,
                        count=2,
                        start_image=frames["start"],
                        end_image=frames["end"],
                    ),
                    frames["project"],
                )
                frames["bound"] = [start, end]
                await page.route("**/batchexecute*", guard)
                submit = page.locator("button").filter(has=_ligature(page, "arrow_forward")).first
                await composer._click(page, submit, named="R12 frame request probe", timeout=5000)
                await asyncio.wait_for(observed, 15)
                frames["evidence"].write_text(
                    json.dumps(
                        {
                            "project": frames["project"],
                            "profile": frames["profile"],
                            "bound_uploads": frames["bound"],
                            "aborted_before_forwarding": frames["aborted"],
                            "local_response": 409,
                            "guard_problem": frames["problem"],
                        }
                    )
                )
            finally:
                await page.unroute("**/batchexecute*", guard)
                client._checkin_page(page)

    asyncio.run(run())


@then("the measured interpolation guard accepts both bound frames and zero submissions forwarded")
def verify_frames(frames):
    assert len(frames["requests"]) == 1
    assert frames["requests"][0] == "nprQif"
    assert frames["problem"] is None
    assert len(set(frames["bound"])) == 2
    assert frames["aborted"] is True
