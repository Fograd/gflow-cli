"""Nano Banana 2.1 retains reference ordering and pre-submission budget guards."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.api import native_image_models, native_image_references
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest, ImageRef, Model
from gflow_cli.api.reference_markers import ReferenceSlot, prepare_image_slot_request
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.server import create_app
from tests.api.test_native_image_models import payload
from tests.api.test_native_image_reference_budget import M1, M2, E, P, _fixtures
from tests.selfhost.test_image_auto_http import AUTH, FIRST, PROJECT, SECOND, config


def test_rest_beluga_defaults_to_auto_and_uses_first_numbered_reference(tmp_path):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        for identifier, dimensions in ((FIRST, (160, 90)), (SECOND, (90, 160))):
            path = tmp_path / (identifier + ".png")
            Image.new("RGB", dimensions).save(path)
            store.asset(identifier, "pro1", PROJECT, str(path), "image/png")
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={
                "prompt": "Use @reference_1 with @reference_2",
                "model": "nano-banana-2.1",
                "reference_2": SECOND,
                "reference_1": FIRST,
                "async": True,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["requestedAspectRatio"] == "auto"
        assert body["resolvedAspectRatio"] == "16:9"
        assert body["aspectPolicy"] == "derived-first-reference-nearest-supported-v1"
        with store.connection() as connection:
            queued = json.loads(connection.execute("SELECT payload FROM jobs").fetchone()[0])
        assert queued["model"] == "nano-banana-2.1"
        assert queued["aspectRatio"] == "16:9"
        assert queued["reference_1"] == FIRST
        assert queued["reference_2"] == SECOND


@pytest.mark.asyncio
async def test_native_beluga_slots_retain_order_and_hydrate_actual_character_weight(monkeypatch):
    client = _fixtures(monkeypatch)
    monkeypatch.setattr(
        native_image_models,
        "_read_native",
        AsyncMock(side_effect=[payload("BELUGA", cap=4), [None, None, None, 2]]),
    )
    request = prepare_image_slot_request(
        GenerateImageRequest(
            prompt="Use @reference_1 with @character_1 and @reference_2",
            model=Model.BELUGA,
            refs=(ImageRef(M2), ImageRef(M1)),
        ),
        {
            "reference_1": ReferenceSlot("image", M2),
            "reference_2": ReferenceSlot("image", M1),
            "character_1": ReferenceSlot("character", E, 1),
        },
    )
    result = await native_image_references.validate_native_image_references(client, P, request)
    assert result.model is Model.BELUGA
    assert tuple(ref.name for ref in result.refs) == (M2, M1)
    assert result.reference_entities == (E,)
    assert result.reference_entity_names == ("Owned",)
    assert result.reference_prompt_plan.spans == request.reference_prompt_plan.spans
    character = next(s for s in result.reference_prompt_plan.slots if s.kind == "character")
    assert character.image_count == 2
    client._checkin_page.assert_called_once_with("page")


@pytest.mark.asyncio
@pytest.mark.parametrize("local_count,capacity", [(9, 10), (2, 3)])
async def test_native_beluga_weighted_overflow_refuses_before_upload_or_mint(
    monkeypatch, tmp_path, local_count, capacity
):
    fake = _fixtures(monkeypatch)
    paths = tuple(tmp_path / f"reference-{i}.png" for i in range(local_count))
    for path in paths:
        Image.new("RGB", (2, 2), "red").save(path)
    monkeypatch.setattr(
        native_image_models,
        "_read_native",
        AsyncMock(side_effect=[payload("BELUGA", cap=capacity), [None, None, None, 2]]),
    )
    client = object.__new__(FlowApiClient)
    client._checkout_page = fake._checkout_page
    client._checkin_page = fake._checkin_page
    client._uses_native_characters = Mock(return_value=True)
    client._mint_recaptcha_token = AsyncMock()
    client.transport = SimpleNamespace(generate_images=AsyncMock(), upload_image=AsyncMock())
    checkpoint = Mock()
    with pytest.raises(ConfigurationError, match="budget exceeded"):
        await client._drive_images_generation_unseeded(
            project_id=P,
            req=GenerateImageRequest(
                prompt="Mixed local and character refs",
                model=Model.BELUGA,
                ref_paths=paths,
                reference_entities=(E,),
            ),
            recaptcha_action="IMAGE_GENERATION",
            on_checkpoint=checkpoint,
        )
    client._mint_recaptcha_token.assert_not_awaited()
    client.transport.generate_images.assert_not_awaited()
    client.transport.upload_image.assert_not_awaited()
    checkpoint.assert_not_called()
    client._checkin_page.assert_called_once_with("page")


def test_eleven_beluga_local_refs_fail_at_request_construction(tmp_path):
    with pytest.raises(ValueError, match="BELUGA allows at most 10 reference"):
        GenerateImageRequest(
            prompt="Too many refs",
            model=Model.BELUGA,
            ref_paths=tuple(tmp_path / f"unused-{i}.png" for i in range(11)),
        )
