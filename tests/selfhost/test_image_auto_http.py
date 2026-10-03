import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

AUTH = {"Authorization": "Bearer test-token"}
PROJECT = "11111111-1111-4111-8111-111111111111"
FIRST = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SECOND = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def config(tmp_path):
    return Settings(
        token="test-token",
        root=tmp_path,
        sync_wait=0,
        accounts={"pro1": {"email": "fixture", "project": PROJECT}},
    )


@pytest.mark.parametrize(
    "model,explicit",
    [("nano-banana-2", False), ("nano-banana-pro", False), ("nano-banana-2-lite", True)],
)
def test_auto_resolves_first_actual_reference_and_retains_policy(tmp_path, model, explicit):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        for identifier, dimensions in ((FIRST, (160, 90)), (SECOND, (90, 160))):
            path = tmp_path / (identifier + ".png")
            Image.new("RGB", dimensions).save(path)
            store.asset(identifier, "pro1", PROJECT, str(path), "image/png")
        payload = {
            "prompt": "x",
            "model": model,
            "reference_2": SECOND,
            "reference_1": FIRST,
            "async": True,
        }
        if explicit:
            payload["aspectRatio"] = "auto"
        response = client.post("/v1/google-flow/images", headers=AUTH, json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["request"]["aspectRatio"] == "auto"
        assert body["requestedAspectRatio"] == "auto"
        assert body["resolvedAspectRatio"] == "16:9"
        assert body["aspectPolicy"] == "derived-first-reference-nearest-supported-v1"
        with store.connection() as connection:
            queued = json.loads(connection.execute("SELECT payload FROM jobs").fetchone()[0])
        assert queued["aspectRatio"] == "16:9"
        store.finish(body["jobId"], "completed", {"media": []})
        completed = client.get(f"/v1/google-flow/jobs/{body['jobId']}", headers=AUTH).json()
        assert completed["response"]["aspectPolicy"] == body["aspectPolicy"]


def test_auto_no_reference_or_invalid_cache_never_enqueues(tmp_path):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        assert (
            client.post(
                "/v1/google-flow/images",
                headers=AUTH,
                json={"prompt": "x", "aspectRatio": "auto", "async": True},
            ).status_code
            == 422
        )
        path = tmp_path / "invalid.png"
        path.write_bytes(b"invalid")
        store.asset(FIRST, "pro1", PROJECT, str(path), "image/png")
        assert (
            client.post(
                "/v1/google-flow/images",
                headers=AUTH,
                json={"prompt": "x", "aspectRatio": "auto", "reference_1": FIRST, "async": True},
            ).status_code
            == 422
        )
        assert store.jobs() == []


def test_lite_default_and_explicit_ratio_do_not_decode_reference(tmp_path):
    with TestClient(create_app(config(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        path = tmp_path / "invalid.png"
        path.write_bytes(b"fixture")
        store.asset(FIRST, "pro1", PROJECT, str(path), "image/png")
        for extra in (
            {"model": "nano-banana-2-lite"},
            {"model": "nano-banana-pro", "aspectRatio": "1:1"},
        ):
            response = client.post(
                "/v1/google-flow/images",
                headers=AUTH,
                json={"prompt": "x", "reference_1": FIRST, "async": True, **extra},
            )
            assert response.status_code == 201
            assert "aspectPolicy" not in response.json()
