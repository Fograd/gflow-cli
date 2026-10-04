"""Plural SDK refuses unsafe singular tracking and validates before browser work."""

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.video import GenerateVideoRequest
from gflow_cli.errors import ConfigurationError


@pytest.mark.asyncio
async def test_singular_method_refuses_count_two_before_any_browser(tmp_path):
    client = FlowApiClient(profile_dir=tmp_path)
    with pytest.raises(ConfigurationError, match="generate_videos_batch"):
        await client.generate_video(req=GenerateVideoRequest(prompt="synthetic", count=2))


@pytest.mark.asyncio
async def test_batch_method_refuses_count_one_before_browser(tmp_path):
    client = FlowApiClient(profile_dir=tmp_path)
    with pytest.raises(ConfigurationError, match="two through four"):
        await client.generate_videos_batch(req=GenerateVideoRequest(prompt="synthetic", count=1))
