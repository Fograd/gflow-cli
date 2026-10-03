"""Explicit promotion preserves existing export defaults."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("resolution", ["720p", "1080p", "4k"])
def test_explicit_promotion_queues_own_kind(tmp_path, resolution):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/videos/upscale",
            headers=AUTH,
            json={
                "mediaGenerationId": M,
                "operation": "promotion",
                "resolution": resolution,
                "captchaToken": "synthetic-native-token-promotion-private",
                "async": True,
            },
        )
        assert result.status_code == 201, result.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == "videos/promote"
        payload = json.loads(job["payload"])
        assert (
            payload["resolution"] == resolution
            and "captchaToken" not in payload
            and "captchaSecret" in payload
        )


@pytest.mark.parametrize("resolution", ["360p", "2k", "gif"])
def test_invalid_promotion_target_refuses_before_queue(tmp_path, resolution):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/videos/upscale",
            headers=AUTH,
            json={
                "mediaGenerationId": M,
                "operation": "promotion",
                "resolution": resolution,
                "async": True,
            },
        )
        assert result.status_code == 422
        assert client.app.state.store.claim("pro1") is None


def test_promotion_requires_explicit_video_enablement(tmp_path):
    cfg = settings(tmp_path)
    cfg.allow_video = False
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/videos/upscale",
            headers=AUTH,
            json={"mediaGenerationId": M, "operation": "promotion", "async": True},
        )
        assert result.status_code == 403
        assert client.app.state.store.claim("pro1") is None
