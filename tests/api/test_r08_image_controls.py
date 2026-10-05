"""R08 controls must refuse malformed choices before browser or queue work."""

from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.errors import QueueSchemaError
from gflow_cli.worker.codec import decode_payload


@pytest.mark.parametrize("count", [True, False, 1.0, 1.5, "2"])
def test_sdk_count_requires_an_actual_integer(count):
    with pytest.raises(ValueError):
        GenerateImageRequest(prompt="fixture", count=count)


@pytest.mark.parametrize("field,value", [("model", "unknown"), ("aspect", "auto")])
def test_sdk_requires_supported_control_enums(field, value):
    with pytest.raises(ValueError):
        GenerateImageRequest(prompt="fixture", **{field: value})


@pytest.mark.parametrize("field", ["model", "aspect"])
@pytest.mark.parametrize("value", ["", False, 0])
def test_queue_does_not_replace_explicit_invalid_choices_with_defaults(field, value):
    with pytest.raises(QueueSchemaError):
        decode_payload("t2i", {"prompt": "fixture", field: value})


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [True, 1.5])
async def test_batch_invalid_count_precedes_project_creation(count):
    client = object.__new__(FlowApiClient)
    client.create_project = AsyncMock()
    with pytest.raises(ValueError):
        await client.generate_images_batch(req=GenerateImageRequest(prompt="fixture"), count=count)
    client.create_project.assert_not_awaited()
