"""UI-owned image submissions never enter the HTTP retry loop."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api import client as module
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.dto import GenerationCheckpoint
from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.errors import NetworkError

P = "11111111-1111-4111-8111-111111111111"


def client_for(host, transport):
    client = FlowApiClient.__new__(FlowApiClient)
    client.settings = SimpleNamespace(flow_host=host)
    client._page = SimpleNamespace(url="https://" + host + "/project/" + P)
    client.transport = transport
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["flow.google.com", "labs.google"])
async def test_page_owned_submit_never_constructs_retry_loop(monkeypatch, host):
    transport = SimpleNamespace(
        uses_page_owned_image_recaptcha=lambda: True,
        generate_images=AsyncMock(side_effect=NetworkError(detail="lost acknowledgement")),
    )
    client = client_for(host, transport)
    checkpoints: list[GenerationCheckpoint] = []

    def forbidden_retry():
        pytest.fail("A browser submit must not enter the HTTP retry loop")

    monkeypatch.setattr(module, "post_with_retry", forbidden_retry)
    with pytest.raises(NetworkError):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(prompt="fixture"),
            recaptcha_action="imageGeneration",
            on_checkpoint=checkpoints.append,
        )
    assert transport.generate_images.await_count == 1
    assert [item.phase for item in checkpoints] == ["submit_attempted"]


@pytest.mark.asyncio
async def test_non_page_owned_transport_keeps_existing_http_retry(monkeypatch):
    from gflow_cli.api._retry import _make_retrying

    image = SimpleNamespace(media_name="m", workflow_id="w")
    transport = SimpleNamespace(
        uses_page_owned_image_recaptcha=lambda: False,
        generate_images=AsyncMock(side_effect=[NetworkError(detail="connection"), [image]]),
    )
    client = client_for("labs.google", transport)
    client._mint_recaptcha_token = AsyncMock(return_value="fixture-token")
    monkeypatch.setattr(
        module, "post_with_retry", lambda: _make_retrying(wait_seconds=lambda _: 0).__aiter__()
    )
    result = await client._drive_images_generation_unseeded(
        project_id=P,
        req=GenerateImageRequest(prompt="fixture"),
        recaptcha_action="imageGeneration",
    )
    assert result == [image]
    assert transport.generate_images.await_count == 2
    client._mint_recaptcha_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_literal_slot_plan_needs_no_ownership_snapshot(monkeypatch):
    from gflow_cli.api import native_image_references
    from gflow_cli.api.reference_markers import resolve_reference_markers

    plan = resolve_reference_markers("literal text", surface="image", slots={})
    transport = SimpleNamespace(
        uses_page_owned_image_recaptcha=lambda: True,
        generate_images=AsyncMock(return_value=[SimpleNamespace(media_name="m", workflow_id="w")]),
    )
    client = client_for("flow.google.com", transport)
    forbidden = AsyncMock(side_effect=AssertionError("No references need ownership resolution"))
    monkeypatch.setattr(native_image_references, "validate_native_image_references", forbidden)
    await client._drive_images_generation_unseeded(
        project_id=P,
        req=GenerateImageRequest(prompt="literal text", reference_prompt_plan=plan),
        recaptcha_action="imageGeneration",
    )
    forbidden.assert_not_awaited()
