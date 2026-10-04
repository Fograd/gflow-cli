import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import Settings, create_app

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
URL = "https://flow-content.google/image/owned?Signature=private"


@pytest.fixture
def native_http(tmp_path, monkeypatch):
    calls = []

    async def run(argv, timeout):
        calls.append(argv)
        return 0, json.dumps(
            {"status": "ok", "mediaGenerationId": M, "url": URL, "kind": "image", "projectId": P}
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls


def get(client, **query):
    return client.get(
        "/v1/google-flow/assets/" + M,
        params={"source": "google", **query},
        headers={"Authorization": "Bearer test"},
    )


def test_native_lookup_not_local_registry(native_http):
    client, calls = native_http
    response = get(client, email="test@example.org", projectId=P)
    assert response.status_code == 200
    assert response.json() == {"url": URL, "mediaGenerationId": M}
    assert calls[0][3] == "asset-get"
    assert json.loads(calls[0][5]) == {"project_id": P, "media_id": M}


def test_native_lookup_requires_account(native_http):
    client, calls = native_http
    assert get(client, projectId=P).status_code == 422
    assert not calls


@pytest.mark.parametrize("raw", ["false", "0", "no"])
def test_native_supplied_invalid_raw(native_http, raw):
    client, calls = native_http
    assert get(client, email="test@example.org", raw=raw).status_code == 400
    assert not calls


def test_native_auth_required(native_http):
    client, calls = native_http
    response = client.get(
        "/v1/google-flow/assets/" + M, params={"source": "google", "email": "test@example.org"}
    )
    assert response.status_code == 401
    assert not calls


@pytest.mark.parametrize("body", [b"", b"not-json", b"[]"])
def test_malformed_private_worker_is_masked_502(native_http, monkeypatch, body):
    client, calls = native_http

    async def failed(argv, timeout):
        return 7, body

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", failed)
    response = get(client, email="test@example.org")
    assert response.status_code == 502
    assert "Signature" not in response.text


def test_native_url_response_not_cached(native_http):
    client, calls = native_http
    assert get(client, email="test@example.org").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "kind,mime,extension",
    [
        ("video", "video/mp4", ".mp4"),
        ("image", "image/png", ".png"),
        ("image", "image/jpeg", ".jpg"),
    ],
)
@pytest.mark.parametrize(
    "range_header,expected", [(None, 200), ("bytes=bad", 400), ("bytes=999999-", 416)]
)
def test_native_raw_content_cleanup(
    tmp_path, monkeypatch, range_header, expected, kind, mime, extension
):
    calls = []

    async def run(argv, timeout):
        payload = json.loads(argv[5])
        if argv[3] == "asset-get":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "mediaGenerationId": M,
                    "projectId": P,
                    "kind": kind,
                    "url": "https://flow-content.google/" + kind + "/owned?Signature=private",
                }
            ).encode()
        directory = __import__("pathlib").Path(payload["output_dir"])
        directory.mkdir(parents=True)
        path = directory / (M + extension)
        path.write_bytes(b"native-video")
        calls.append(directory)
        return 0, json.dumps(
            {
                "status": "ok",
                "mediaGenerationId": M,
                "projectId": P,
                "kind": kind,
                "path": str(path),
                "mimeType": mime,
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "test@example.org", "project": P}},
        callbacks=(),
        sync_wait=0,
    )
    headers = {"Authorization": "Bearer test"}
    if range_header:
        headers["Range"] = range_header
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.get(
            "/v1/google-flow/assets/" + M,
            params={"source": "google", "email": "test@example.org", "raw": "true"},
            headers=headers,
        )
        assert response.status_code == expected
        if expected == 200:
            assert response.headers["content-type"] == mime
            assert response.content == b"native-video"
            assert response.headers["cache-control"] == "no-store"
    assert calls and not calls[0].exists()


@pytest.mark.parametrize("raw", [None, "true"])
def test_native_audio_is_an_explicit_http_contract_refusal(native_http, monkeypatch, raw):
    client, calls = native_http

    async def run(argv, timeout):
        calls.append(argv)
        return 0, json.dumps(
            {
                "status": "ok",
                "mediaGenerationId": M,
                "projectId": P,
                "kind": "audio",
                "url": "https://audio.example.test/sample?secret=private",
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    response = get(client, email="test@example.org", **({} if raw is None else {"raw": raw}))
    assert response.status_code == 400
    assert "audio" in response.json()["detail"]
    assert "secret" not in response.text
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "video"),
        ("mimeType", "image/webp"),
        ("mimeType", "video/mp4"),
        ("mediaGenerationId", P),
        ("projectId", M),
        ("path", "/etc/passwd"),
    ],
)
def test_raw_image_rechecks_download_identity_and_content_type(
    native_http, monkeypatch, tmp_path, field, value
):
    from pathlib import Path

    client, calls = native_http
    directories = []

    async def run(argv, timeout):
        calls.append(argv)
        if argv[3] == "asset-get":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "mediaGenerationId": M,
                    "projectId": P,
                    "kind": "image",
                    "url": URL,
                }
            ).encode()
        directory = Path(json.loads(argv[5])["output_dir"])
        directory.mkdir(parents=True)
        path = directory / "image.png"
        path.write_bytes(b"private-content")
        directories.append(directory)
        result = {
            "status": "ok",
            "mediaGenerationId": M,
            "projectId": P,
            "kind": "image",
            "mimeType": "image/png",
            "path": str(path),
        }
        result[field] = value
        return 0, json.dumps(result).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    response = get(client, email="test@example.org", raw="true")
    assert response.status_code == 502
    assert "private-content" not in response.text
    assert directories and not directories[0].exists()
