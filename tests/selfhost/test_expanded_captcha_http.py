"""HTTP provider controls reach the newly guarded generic-video/upscale workers."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

M = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize(
    "route,body",
    [
        ("videos", {"prompt": "fixture", "model": "veo-3.1-lite", "count": 1}),
        ("images/upscale", {"mediaGenerationId": M, "resolution": "2k"}),
        ("images/upscale", {"mediaGenerationId": M, "resolution": "4k"}),
    ],
)
@pytest.mark.parametrize(
    "controls", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 2}, {"captchaRetry": 10}]
)
def test_provider_controls_preserve_guarded_worker_policy(
    tmp_path, monkeypatch, route, body, controls
):
    monkeypatch.setattr(
        "gflow_cli.selfhost.captcha_routes.provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/" + route, headers=AUTH, json={**body, **controls, "async": True}
        )
        assert response.status_code == 201, response.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == route
        queued = json.loads(job["payload"])
        for name, value in controls.items():
            assert queued[name] == value


@pytest.mark.parametrize(
    "controls",
    [
        {"captchaRetry": True},
        {"captchaRetry": 0},
        {"captchaRetry": 11},
        {"captchaOrder": "Unknown"},
        {"captchaOrder": "CapSolver,CapSolver"},
        {"captchaRetry": 2, "captchaOrder": "CapSolver"},
    ],
)
@pytest.mark.parametrize(
    "route,body",
    [
        ("videos", {"prompt": "fixture"}),
        ("images/upscale", {"mediaGenerationId": M, "resolution": "4k"}),
    ],
)
def test_invalid_controls_do_not_queue(tmp_path, monkeypatch, route, body, controls):
    monkeypatch.setattr(
        "gflow_cli.selfhost.captcha_routes.provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/" + route, headers=AUTH, json={**body, **controls, "async": True}
        )
        assert response.status_code == 422, response.text
        assert client.app.state.store.jobs() == []
        assert not list((cfg.root / "captcha-input").glob("*.token"))


@pytest.mark.parametrize("controls", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 2}])
def test_generic_video_plural_control_refuses_before_queue(tmp_path, controls):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={"prompt": "fixture", "count": 2, **controls, "async": True},
        )
        assert response.status_code == 501
        assert client.app.state.store.jobs() == []
