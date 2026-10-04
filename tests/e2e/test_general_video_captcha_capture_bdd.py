"""Opt-in real generic T2V envelope proof; all batchexecute routes are aborted.

No generated media or solver calls. The route is installed only at submit time.
Never print bodies, project IDs, browser tokens, or authenticated URLs.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest
from pytest_bdd import given, scenario, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports import migrated_video_overrides as overrides
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel
from gflow_cli.errors import WireFormatError

pytestmark = pytest.mark.e2e_auth


@scenario(
    "../features/general_video_captcha_capture.feature",
    "Capture the current text-to-video envelope and abort before Google dispatch",
)
def test_generic_video_capture():
    pass


@given("an explicitly configured authenticated native Flow project", target_fixture="capture")
def configured_capture():
    if os.getenv("GFLOW_E2E_GENERIC_VIDEO_CAPTURE") != "1":
        pytest.skip("explicit generic video capture opt-in required")
    home = os.getenv("GFLOW_E2E_PROFILE_DIR")
    project = os.getenv("GFLOW_E2E_PROJECT_ID")
    if not home or not project:
        pytest.skip("private authenticated profile directory and project are required")
    return {"home": Path(home), "project": project, "validated": 0, "forwarded": 0}


@when("a one-output generic video request is intercepted before dispatch")
def capture_without_dispatch(capture, monkeypatch):
    async def exercise():
        def validated(body):
            frames = json.loads(parse_qs(body)["f.req"][0])
            args = json.loads(frames[0][0][1])
            assert frames[0][0][0] in overrides.VIDEO_SUBMIT_RPCS
            assert args[1][5] == capture["project"]
            assert len(args[0]) == 1
            capture["validated"] += 1
            target = os.getenv("GFLOW_E2E_CAPTURE_OUTPUT")
            if target:
                output = Path(target)
                output.write_text(json.dumps({"rpc": frames[0][0][0], "args": args}))
                output.chmod(0o600)

        async def token(_page):
            raise WireFormatError(detail="Expected free generic CAPTCHA capture abort")

        override = overrides.VideoOverrides(
            project=capture["project"], count=1, token=token, on_validated=validated
        )
        original = overrides.guard_video_submit

        async def abort_all(route, request, page, current):
            # Unknown/unrelated RPCs abort; known submits fail in token() before forwarding.
            async def refuse_forward(**_kwargs):
                capture["forwarded"] += 1
                raise AssertionError("Aborted capture must never forward a request")

            shim = SimpleNamespace(fallback=route.abort, continue_=refuse_forward)
            await original(shim, request, page, current)

        monkeypatch.setattr(overrides, "guard_video_submit", abort_all)
        state = overrides.active_video_overrides.set(override)
        try:
            async with FlowApiClient(profile_dir=capture["home"], headless=False) as client:
                request = GenerateVideoRequest(
                    prompt="A simple blue circle on a white background.",
                    mode=Mode.T2V,
                    aspect=Aspect.LANDSCAPE,
                    model=VideoModel.VEO_3_1_LITE,
                    count=1,
                )
                with pytest.raises(WireFormatError):
                    await client.generate_video(
                        req=request,
                        project_id=capture["project"],
                        download=False,
                        poll_timeout_s=30,
                    )
            assert not override.dispatched
        finally:
            overrides.active_video_overrides.reset(state)

    asyncio.run(exercise())


@then("its known RPC project count and CAPTCHA context are verified without forwarding")
def proven_capture(capture):
    assert capture["validated"] == 1
    assert capture["forwarded"] == 0
