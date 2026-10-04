"""Opt-in authenticated batch request proof; aborts before Google forwarding."""

import os
from pathlib import Path
from uuid import UUID

import pytest
from pytest_bdd import given, scenario, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.native_video_batch_driver import batch_submit_probe
from gflow_cli.api.video import Aspect, GenerateVideoRequest, VideoModel


class BatchProbeCompleteError(Exception):
    pass


@pytest.mark.e2e_auth
@scenario(
    "../features/native_video_batch_preflight.feature",
    "Four requested outputs bind to one exact intercepted request",
)
def test_native_batch_request_only():
    pass


@given(
    "an explicitly configured authenticated native batch project", target_fixture="batch_fixture"
)
def batch_fixture():
    profile = os.environ.get("GFLOW_E2E_BATCH_PROFILE_DIR")
    project = os.environ.get("GFLOW_E2E_BATCH_PROJECT_ID")
    if not profile or not project:
        pytest.skip("Private native batch preflight environment is not configured")
    return {"profile": Path(profile), "project": str(UUID(project)), "requests": []}


@when("four generic video outputs are prepared and the exact request is aborted")
def run_batch(batch_fixture):
    import asyncio

    def probe(request):
        batch_fixture["requests"].append(request)
        raise BatchProbeCompleteError()

    async def run():
        async with FlowApiClient(profile_dir=batch_fixture["profile"], headless=False) as client:
            state = batch_submit_probe.set(probe)
            try:
                with pytest.raises(BatchProbeCompleteError) as stopped:
                    await client.generate_videos_batch(
                        req=GenerateVideoRequest(
                            prompt="A small blue ceramic cup on a plain table",
                            count=4,
                            aspect=Aspect.LANDSCAPE,
                            model=VideoModel.VEO_3_1_LITE,
                        ),
                        project_id=batch_fixture["project"],
                        download=False,
                    )
                batch_fixture["aborted"] = (
                    "Native batch request aborted before forwarding"
                    in getattr(stopped.value, "__notes__", [])
                )
            finally:
                batch_submit_probe.reset(state)

    asyncio.run(run())


@then("four distinct assigned output identities were observed and zero submissions forwarded")
def verified(batch_fixture):
    assert len(batch_fixture["requests"]) == 1
    request = batch_fixture["requests"][0]
    assert request.rpcid == "YhhmEf" and request.project_id == batch_fixture["project"]
    assert len(request.media_ids) == 4 and len(set(request.media_ids)) == 4
    assert batch_fixture["aborted"] is True
