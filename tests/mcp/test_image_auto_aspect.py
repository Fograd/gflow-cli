from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from gflow_cli.api.image import Aspect
from gflow_cli.mcp import tools
from gflow_cli.worker.codec import build_image_request


@pytest.mark.parametrize("wait", [True, False])
async def test_auto_resolves_before_queue_and_survives_codec(wait, tmp_path, monkeypatch):
    path = tmp_path / "landscape.png"
    Image.new("RGB", (160, 90)).save(path)
    run = AsyncMock(return_value={"status": "completed" if wait else "pending"})
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_generate_image(
        prompt="fixture",
        aspect="auto",
        reference_images=[str(path)],
        profile="fixture",
        wait=wait,
    )
    payload = run.call_args.kwargs["payload"]
    assert payload["aspect"] == "16:9"
    assert payload["aspect_decision"]["requestedAspectRatio"] == "auto"
    assert build_image_request(payload).aspect is Aspect.LANDSCAPE
    assert result["resolvedAspectRatio"] == "16:9"
    assert result["requestedAspectRatio"] == "auto"


@pytest.mark.parametrize("refs", [None, ["00000000-0000-4000-8000-000000000001"]])
async def test_unresolvable_auto_never_resolves_profile_or_queues(refs, monkeypatch):
    profile = Mock()
    run = AsyncMock()
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", profile)
    monkeypatch.setattr(tools, "_run_generation_task", run)
    result = await tools.gflow_generate_image(
        prompt="fixture", aspect="auto", reference_images=refs
    )
    assert result["status"] == "error"
    profile.assert_not_called()
    run.assert_not_called()
