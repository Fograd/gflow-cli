"""Native token controls stay outside durable job payloads and are removed safely."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.native_captcha import native_secret_path
from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
TOKEN = "synthetic-native-captcha-private-token"


def request(kind):
    if kind == "voices/create":
        return "/voices", {
            "displayName": "Fixture",
            "voice": "Charon",
            "dialog": "Hello",
            "voicePerformance": "Calm",
        }
    if kind == "videos/extend":
        return "/videos/extend", {
            "mediaGenerationId": M,
            "prompt": "Continue",
            "modelKey": "native",
        }
    if kind == "videos/edit":
        return "/videos", {
            "referenceVideo_1": M,
            "prompt": "Edit",
            "model": "omni-flash",
            "modelKey": "native",
            "endFrameIndex_1": 24,
        }
    return "/videos", {
        "prompt": "Use @referenceAudio_3",
        "model": "omni-flash",
        "referenceAudio_3": "Charon",
    }


@pytest.mark.parametrize(
    "kind", ["voices/create", "videos/extend", "videos/edit", "videos/reference"]
)
def test_supplied_token_is_private_and_not_in_queue_or_response(tmp_path, kind):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    endpoint, body = request(kind)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow" + endpoint,
            headers=AUTH,
            json={**body, "captchaToken": TOKEN, "async": True},
        )
        assert result.status_code == 201, result.text
        assert TOKEN not in result.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == kind
        assert TOKEN not in job["payload"]
        payload = json.loads(job["payload"])
        assert "captchaToken" not in payload
        path = native_secret_path(payload, cfg.root)
        assert path.read_text() == TOKEN and path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "kind", ["voices/create", "videos/extend", "videos/edit", "videos/reference"]
)
def test_invalid_or_unverified_controls_do_not_enqueue(tmp_path, kind, monkeypatch):
    from gflow_cli.selfhost import captcha_routes

    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    cfg = settings(tmp_path)
    cfg.allow_video = True
    endpoint, body = request(kind)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for controls, status in (
            ({"captchaToken": "short"}, 422),
            ({"captchaToken": TOKEN + " whitespace"}, 422),
            ({"captchaRetry": 11}, 422),
            ({"captchaOrder": "CapSolver,CapSolver"}, 422),
            ({"captchaToken": TOKEN, "captchaRetry": 1}, 422),
        ):
            result = client.post(
                "/v1/google-flow" + endpoint, headers=AUTH, json={**body, **controls, "async": True}
            )
            assert result.status_code == status, result.text
        assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["edit", "reference", "extension", "voice"])
async def test_worker_uses_one_bound_token_and_removes_private_file(tmp_path, monkeypatch, kind):
    from gflow_cli.selfhost import (
        extension_worker as xw,
    )
    from gflow_cli.selfhost import (
        native_video_edit_worker as ew,
    )
    from gflow_cli.selfhost import (
        native_worker as vw,
    )
    from gflow_cli.selfhost import (
        reference_video_worker as rw,
    )

    cfg = settings(tmp_path)
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(cfg.root))
    directory = cfg.root / "captcha-input"
    directory.mkdir()
    path = directory / (hashlib.sha256(TOKEN.encode()).hexdigest() + ".token")
    path.write_text(TOKEN)
    path.chmod(0o600)
    payload = {"captchaSecret": str(path), "project_id": P}
    action = "AUDIO_GENERATION" if kind == "voice" else "VIDEO_GENERATION"

    async def operation(*args):
        assert not path.exists()
        page = SimpleNamespace(url="https://flow.google.com/project/" + P, evaluate=AsyncMock())
        assert await TokenMinter(page).mint(action) == TOKEN
        with pytest.raises(ConfigurationError):
            await TokenMinter(page).mint(action)
        page.evaluate.assert_not_awaited()
        return {"ok": True}

    if kind == "voice":
        monkeypatch.setattr(vw, "_execute", operation)
        result = await vw.execute("voice-saved-create", "pro1", payload)
    else:
        worker, public, private = (
            (ew, "run_edit", "_run_edit")
            if kind == "edit"
            else (rw, "run_reference_video", "_run_reference_video")
            if kind == "reference"
            else (xw, "run_extension", "_run_extension")
        )
        monkeypatch.setattr(worker, private, operation)
        result = await getattr(worker, public)("pro1", P, payload, tmp_path)
    assert result == {"ok": True} and not path.exists()


@pytest.mark.parametrize("value", ["/tmp/token", "../token", "bad", 42])
def test_private_worker_path_cannot_read_arbitrary_files(tmp_path, value):
    with pytest.raises(ConfigurationError):
        native_secret_path({"captchaSecret": value}, tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["startup", "cancel"])
async def test_runtime_cleans_private_token_on_failed_start_or_cancel(
    tmp_path, monkeypatch, failure
):
    import asyncio

    from gflow_cli.selfhost import runtime

    cfg = settings(tmp_path)
    directory = cfg.root / "captcha-input"
    directory.mkdir()
    path = directory / (hashlib.sha256(TOKEN.encode()).hexdigest() + ".token")
    path.write_text(TOKEN)
    path.chmod(0o600)
    error = asyncio.CancelledError if failure == "cancel" else OSError

    async def fail(*_):
        raise error

    monkeypatch.setattr(runtime, "_execute", fail)
    with pytest.raises(error):
        await runtime.execute(cfg, None, {"payload": json.dumps({"captchaSecret": str(path)})})
    assert not path.exists()


@pytest.mark.parametrize(
    "kind", ["voices/create", "videos/extend", "videos/edit", "videos/reference"]
)
@pytest.mark.parametrize(
    "controls", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 2}, {"captchaRetry": 10}]
)
def test_explicit_provider_controls_enqueue_without_secrets(tmp_path, kind, controls, monkeypatch):
    from gflow_cli.selfhost import captcha_routes

    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    cfg = settings(tmp_path)
    cfg.allow_video = True
    endpoint, body = request(kind)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow" + endpoint, headers=AUTH, json={**body, **controls, "async": True}
        )
        assert result.status_code == 201, result.text
        job = client.app.state.store.claim("pro1")
        assert job["kind"] == kind
        queued = json.loads(job["payload"])
        assert all(queued[key] == value for key, value in controls.items())
        assert "captchaSecret" not in queued and "captchaToken" not in queued


@pytest.mark.parametrize("count,status", [(1, 201), (2, 501)])
def test_general_video_supplied_token_has_one_output_scope(tmp_path, count, status):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "prompt": "A simple circle",
                "model": "veo-3.1-lite",
                "count": count,
                "captchaToken": TOKEN,
                "async": True,
            },
        )
        assert result.status_code == status, result.text
        assert TOKEN not in result.text
        if status == 201:
            job = client.app.state.store.claim("pro1")
            assert job["kind"] == "videos" and TOKEN not in job["payload"]
            payload = json.loads(job["payload"])
            path = native_secret_path(payload, cfg.root)
            assert path.read_text() == TOKEN and path.stat().st_mode & 0o777 == 0o600
        else:
            assert (
                client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []
            )


@pytest.mark.parametrize(
    "controls,resolution,status",
    [
        ({"captchaToken": TOKEN}, "2k", 201),
        ({"captchaOrder": "CapSolver"}, "2k", 201),
        ({"captchaRetry": 1}, "2k", 201),
        ({"captchaRetry": 2}, "2k", 501),
        ({"captchaToken": TOKEN}, "4k", 501),
    ],
)
def test_image_upscale_captcha_scope_is_measured_2k_once(
    tmp_path, monkeypatch, controls, resolution, status
):
    from gflow_cli.selfhost import captcha_routes

    monkeypatch.setattr(
        captcha_routes,
        "provider_keys",
        lambda: SimpleNamespace(public=lambda: {"CapSolver": {"configured": True}}),
    )
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/images/upscale",
            headers=AUTH,
            json={"mediaGenerationId": M, "resolution": resolution, "async": True, **controls},
        )
        assert result.status_code == status, result.text
        assert TOKEN not in result.text
        if status == 201:
            job = client.app.state.store.claim("pro1")
            assert job["kind"] == "images/upscale" and TOKEN not in job["payload"]
        else:
            assert client.app.state.store.jobs() == []
