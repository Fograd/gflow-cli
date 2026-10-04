"""UseAPI-compatible native upscale default; explicit export remains available."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_native_alias_inputs_http import VIDEO, Q
from tests.selfhost.test_native_alias_inputs_http import api as _alias_api
from tests.selfhost.test_server import AUTH, settings

api = _alias_api
M = "22222222-2222-4222-8222-222222222222"


def post(client, payload, route="upscale"):
    return client.post(
        "/v1/google-flow/videos/" + route,
        headers=AUTH,
        json={"mediaGenerationId": M, "async": True, **payload},
    )


@pytest.mark.parametrize(
    "payload,expected,resolution",
    [
        ({}, "videos/promote", "1080p"),
        ({"operation": "export"}, "videos/upscale", "1080p"),
    ],
)
def test_upscale_default_and_explicit_export_route(tmp_path, payload, expected, resolution):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = post(client, payload)
        assert response.status_code == 201, response.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == expected
        data = json.loads(job["payload"])
        assert data["resolution"] == resolution
        assert data["operation"] == ("promotion" if expected == "videos/promote" else "export")


def test_default_promotion_requires_video_enablement(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert post(client, {}).status_code == 403
        assert client.app.state.store.jobs() == []


def test_explicit_export_and_gif_keep_unbilled_route_when_video_disabled(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert post(client, {"operation": "export"}).status_code == 201
        assert post(client, {}, route="gif").status_code == 201
        store = client.app.state.store
        export = store.claim("pro1")
        assert export["kind"] == "videos/upscale"
        store.finish(export["id"], "completed", {})
        gif = store.claim("pro1")
        assert gif["kind"] == "videos/gif"
        assert json.loads(gif["payload"])["resolution"] == "270p"


@pytest.mark.parametrize("operation", [None, "unknown", "", True, {}])
def test_invalid_operation_has_no_job(tmp_path, operation):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        assert post(client, {"operation": operation}).status_code == 422
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("controls", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 2}])
def test_default_native_alias_and_provider_controls_preserve_scope(api, monkeypatch, controls):
    from gflow_cli.selfhost import captcha_routes

    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": "***configured***"}),
    )
    client, calls, _ = api
    response = client.post(
        "/v1/google-flow/videos/upscale",
        headers={"Authorization": "Bearer test"},
        json={
            "mediaGenerationId": VIDEO,
            **controls,
            "async": True,
        },
    )
    assert response.status_code == 201, response.text
    job = client.app.state.store.claim("pro1")
    assert job["kind"] == "videos/promote"
    data = json.loads(job["payload"])
    assert data["project"] == Q and data["resolution"] == "1080p"
    assert all(data[key] == value for key, value in controls.items())
    assert len(calls) == 1
    assert "user:" not in job["payload"] and "https:" not in job["payload"]
