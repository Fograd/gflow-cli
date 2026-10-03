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


@pytest.mark.parametrize("wait", [True, False])
async def test_native_uuid_auto_resolved_before_direct_or_queued_submit(
    wait, tmp_path, monkeypatch
):
    from unittest.mock import MagicMock

    from gflow_cli.api.image_aspect_policy import derive_aspect

    project = "11111111-1111-4111-8111-111111111111"
    media = "22222222-2222-4222-8222-222222222222"
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.resolve_native_image_aspect = AsyncMock(
        return_value=(Aspect.from_cli("3:4"), derive_aspect(300, 400))
    )
    run = AsyncMock(return_value={"status": "completed" if wait else "pending"})
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: client)
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_generate_image(
        prompt="fixture", aspect="auto", reference_images=[media], project=project, wait=wait
    )
    client.resolve_native_image_aspect.assert_awaited_once_with(project, media)
    payload = run.call_args.kwargs["payload"]
    assert payload["aspect"] == "3:4"
    assert payload["aspect_decision"]["requestedAspectRatio"] == "auto"
    assert result["resolvedAspectRatio"] == "3:4"


async def test_native_uuid_auto_resolution_error_never_queues(monkeypatch):
    from unittest.mock import MagicMock

    from gflow_cli.errors import ConfigurationError

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.resolve_native_image_aspect = AsyncMock(
        side_effect=ConfigurationError(detail="No dimensions")
    )
    run = AsyncMock()
    monkeypatch.setattr(tools, "FlowApiClient", lambda **kwargs: client)
    monkeypatch.setattr(tools, "_run_generation_task", run)
    monkeypatch.setattr(tools, "_resolve_and_validate_profile", lambda profile: "fixture")
    monkeypatch.setattr(tools._rate_limiter, "acquire", AsyncMock(return_value=True))
    result = await tools.gflow_generate_image(
        prompt="fixture",
        aspect="auto",
        reference_images=["22222222-2222-4222-8222-222222222222"],
        project="11111111-1111-4111-8111-111111111111",
    )
    assert result["status"] == "error"
    run.assert_not_called()
