"""Native promotion HTTP controls reach policy; image/export guards stay scoped."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost import captcha_routes
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

M = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": "***configured***"}),
    )
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as api:
        yield api


@pytest.mark.parametrize(
    "controls", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 2}, {"captchaRetry": 10}]
)
def test_promotion_controls_enqueue_native_kind_without_secrets(client, controls):
    response = client.post(
        "/v1/google-flow/videos/upscale",
        headers=AUTH,
        json={"mediaGenerationId": M, "operation": "promotion", "async": True, **controls},
    )
    assert response.status_code == 201, response.text
    job = client.app.state.store.claim("pro1")
    assert job["kind"] == "videos/promote"
    payload = json.loads(job["payload"])
    assert all(payload[key] == value for key, value in controls.items())
    assert "captchaToken" not in payload and "captchaSecret" not in payload


def test_promotion_duplicate_provider_order_refuses_before_queue(client):
    response = client.post(
        "/v1/google-flow/videos/upscale",
        headers=AUTH,
        json={
            "mediaGenerationId": M,
            "operation": "promotion",
            "captchaOrder": "CapSolver,CapSolver",
            "async": True,
        },
    )
    assert response.status_code == 422
    assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("route", ["videos"])
def test_other_generation_paths_do_not_inherit_native_retry_enablement(client, route):
    response = client.post(
        "/v1/google-flow/" + route,
        headers=AUTH,
        json={"prompt": "Fixture", "captchaRetry": 2, "async": True},
    )
    assert response.status_code == 501, response.text
    assert client.app.state.store.jobs() == []
