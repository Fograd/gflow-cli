"""Actual HTTP byte normalization into durable uploads."""

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings


def test_webp_upload_normalizes_native_bytes_and_reports_conversion(tmp_path, monkeypatch):
    seen = []

    async def execute(cfg, store, job):
        seen.append(json.loads(job["payload"]))
        return {"uploaded": True}

    monkeypatch.setattr("gflow_cli.selfhost.runtime.execute", execute)
    output = BytesIO()
    Image.new("RGBA", (8, 8), (2, 3, 4, 120)).save(output, format="WEBP", lossless=True)
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/v1/google-flow/assets/test@example.org",
            headers={**AUTH, "Content-Type": "image/webp"},
            content=output.getvalue(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["contentType"] == "image/png"
        assert response.json()["sourceContentType"] == "image/webp"
        assert response.json()["converted"] is True
        assert seen[0]["mime"] == "image/png"
        with Image.open(Path(seen[0]["input"])) as image:
            assert image.format == "PNG"
            assert image.getpixel((0, 0))[3] == 120


def test_invalid_webp_refuses_without_queue(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/assets",
            headers={**AUTH, "Content-Type": "image/webp"},
            content=b"not webp",
        )
        assert response.status_code == 422
        assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []
