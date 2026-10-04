"""REST general video aliases and explicit native720 default preserve existing worker semantics."""

import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

M = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"
VEO = ("veo-3.1-fast", "veo-3.1-lite", "veo-3.1-quality", "veo-3.1-lite-low-priority")


def api(root):
    cfg = settings(root)
    cfg.allow_video = True
    return cfg


def queued(store, identifier):
    with store.connection() as conn:
        return json.loads(
            conn.execute("SELECT payload FROM jobs WHERE id=?", (identifier,)).fetchone()[0]
        )


def post(client, **controls):
    return client.post(
        "/v1/google-flow/videos",
        headers=AUTH,
        json={"prompt": "A calm scene", "async": True, **controls},
    )


@pytest.mark.parametrize("alias,canonical", [("landscape", "16:9"), ("portrait", "9:16")])
def test_general_video_aspect_aliases_are_canonical_before_enqueue(tmp_path, alias, canonical):
    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        response = post(client, aspectRatio=alias)
        assert response.status_code == 201, response.text
        assert queued(client.app.state.store, response.json()["jobId"])["aspectRatio"] == canonical


@pytest.mark.parametrize("model", VEO)
def test_explicit_veo720_uses_existing_omitted_wire_default(tmp_path, model):
    from gflow_cli.selfhost.config import VIDEO_ALIASES
    from gflow_cli.worker.codec import build_video_request

    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        response = post(client, model=model, resolution="720p")
        assert response.status_code == 201, response.text
        payload = queued(client.app.state.store, response.json()["jobId"])
        assert "resolution" not in payload
        request = build_video_request(
            {**payload, "model": VIDEO_ALIASES[model], "aspect": payload["aspectRatio"]}
        )
        assert request.resolution is None


@pytest.mark.parametrize("mode", ["i2v", "i2v-fl", "r2v"])
def test_general_veo_frames_and_ingredients_keep_alias_and720_default(tmp_path, mode):
    from PIL import Image

    cfg = api(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for media in (M, N):
            path = tmp_path / (media + ".jpg")
            Image.new("RGB", (2, 2), "red").save(path)
            client.app.state.store.asset(
                media, "pro1", cfg.accounts["pro1"]["project"], str(path), "image/jpeg"
            )
        controls = (
            {"referenceImage_1": M}
            if mode == "r2v"
            else {"startImage": M, **({"endImage": N} if mode == "i2v-fl" else {})}
        )
        response = post(
            client, model="veo-3.1-fast", aspectRatio="portrait", resolution="720p", **controls
        )
        assert response.status_code == 201, response.text
        payload = queued(client.app.state.store, response.json()["jobId"])
        assert payload["aspectRatio"] == "9:16" and "resolution" not in payload
        assert all(payload[key] == value for key, value in controls.items())


@pytest.mark.parametrize("resolution", ["360p", "720p"])
def test_omni_generic_resolution_remains_an_explicit_ui_control(tmp_path, resolution):
    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        response = post(client, model="omni-flash", aspectRatio="landscape", resolution=resolution)
        assert response.status_code == 201, response.text
        payload = queued(client.app.state.store, response.json()["jobId"])
        assert payload["resolution"] == resolution and payload["aspectRatio"] == "16:9"


@pytest.mark.parametrize("aspect", ["1:1", "4:3", "3:4", "auto", "LANDSCAPE", None, True, [], {}])
def test_general_video_does_not_invent_other_aspect_support(tmp_path, aspect):
    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        assert post(client, aspectRatio=aspect).status_code == 422
        assert client.app.state.store.jobs() == []


@pytest.mark.parametrize("resolution", ["360p", "1080p", "4k", "4K", 720, True, [], {}])
def test_veo_nondefault_resolution_refuses_before_enqueue(tmp_path, resolution):
    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        assert post(client, resolution=resolution).status_code == 422
        assert client.app.state.store.jobs() == []


def test_generic_numeric_seed_remains_explicitly_unsupported(tmp_path):
    with TestClient(create_app(api(tmp_path), start_workers=False)) as client:
        assert post(client, seed=0).status_code == 501
        assert client.app.state.store.jobs() == []


@pytest.mark.asyncio
async def test_normalized_video_defaults_reach_existing_cli_without_resolution_flag(
    tmp_path, monkeypatch
):
    from gflow_cli.selfhost.runtime import execute

    cfg = api(tmp_path)
    calls = []

    async def run(args, timeout, **kwargs):
        calls.append(args)
        return 1, b"offline fake refusal"

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = post(client, aspectRatio="landscape", resolution="720p")
        assert response.status_code == 201, response.text
        result = await execute(cfg, client.app.state.store, client.app.state.store.claim("pro1"))
    assert "error" in result and len(calls) == 1
    argv = calls[0]
    assert argv[2:5] == ["gflow_cli.cli", "video", "t2v"]
    assert argv[argv.index("--aspect") + 1] == "16:9"
    assert "--resolution" not in argv
