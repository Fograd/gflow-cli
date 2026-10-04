import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.admin import create_app
from gflow_cli.selfhost.captcha import ProviderKeys

URL = "http://127.0.0.1:8845"


def headers(client):
    page = client.get("/")
    csrf = re.search(r'name="csrf-token" content="([a-f0-9]+)"', page.text)[1]
    return {"Origin": URL, "X-CSRF-Token": csrf}


def test_save_mask_check_and_remove_without_paid_task(tmp_path):
    calls = []

    def remote(request):
        calls.append(request)
        assert request.url == "https://api.capsolver.com/getBalance"
        assert json.loads(request.content) == {"clientKey": "private-capsolver-key"}
        return httpx.Response(
            200,
            json={
                "errorId": 0,
                "balance": 3.125,
                "packages": [{"token": "private-package-secret"}],
            },
        )

    keys = ProviderKeys(tmp_path)
    connection = httpx.AsyncClient(transport=httpx.MockTransport(remote))
    with TestClient(create_app(keys, client=connection), base_url=URL) as client:
        h = headers(client)
        assert not client.get("/api/status").json()["configured"]
        saved = client.post("/api/save", headers=h, json={"key": "private-capsolver-key"})
        assert saved.status_code == 200
        assert "private-capsolver-key" not in saved.text
        assert keys.path.stat().st_mode & 0o777 == 0o600
        assert client.get("/api/status").json()["generationEnabled"] is True
        assert "private-capsolver-key" not in client.get("/").text
        checked = client.post("/api/check", headers=h, json={})
        assert checked.json() == {"verified": True, "balance": 3.125, "generationEnabled": True}
        assert "private-package-secret" not in checked.text
        assert len(calls) == 1
        assert client.post("/api/remove", headers=h, json={}).json() == {"configured": False}
        assert keys.public() == {}
        assert client.get("/api/status").json()["generationEnabled"] is False


@pytest.mark.parametrize("origin", [None, "null", "https://malicious.example", URL + ".evil"])
def test_mutation_requires_exact_origin_and_csrf(tmp_path, origin):
    keys = ProviderKeys(tmp_path)
    with TestClient(create_app(keys), base_url=URL) as client:
        h = headers(client)
        if origin is None:
            h.pop("Origin")
        else:
            h["Origin"] = origin
        assert client.post("/api/save", headers=h, json={"key": "must-not-save"}).status_code == 403
        assert keys.public() == {}
        assert (
            client.post("/api/save", headers={"Origin": URL}, json={"key": "secret"}).status_code
            == 403
        )


def test_bad_host_bounds_schema_and_security_headers(tmp_path):
    keys = ProviderKeys(tmp_path)
    with TestClient(create_app(keys), base_url=URL) as client:
        assert client.get("/", headers={"Host": "malicious.example:8845"}).status_code == 400
        h = headers(client)
        oversized = client.post(
            "/api/save", headers={**h, "Content-Type": "application/json"}, content=b"x" * 2049
        )
        assert oversized.status_code == 413
        malformed = client.post("/api/save", headers=h, json={"key": "secret", "extra": "secret"})
        assert malformed.status_code == 422
        assert "secret" not in malformed.text
        assert client.post("/api/check", headers=h, json={}).status_code == 422
        page = client.get("/")
        assert page.headers["cache-control"] == "no-store"
        assert page.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert "localStorage" not in page.text
        assert keys.public() == {}


def test_provider_error_body_never_reflected(tmp_path):
    keys = ProviderKeys(tmp_path)
    keys.update({"CapSolver": "private-key"})
    connection = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"errorId": 1, "errorDescription": "private-key"})
        )
    )
    with TestClient(create_app(keys, client=connection), base_url=URL) as client:
        failed = client.post("/api/check", headers=headers(client), json={})
        assert failed.status_code == 502
        assert "private-key" not in failed.text


def test_non_ascii_csrf_is_denied_without_server_error(tmp_path):
    keys = ProviderKeys(tmp_path)
    with TestClient(create_app(keys), base_url=URL) as client:
        result = client.post(
            "/api/save",
            headers={b"Origin": URL.encode(), b"X-CSRF-Token": bytes([255])},
            json={"key": "must-not-save"},
        )
        assert result.status_code == 403
        assert keys.public() == {}


def test_only_one_balance_check_can_run(tmp_path):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    started, release = threading.Event(), threading.Event()

    async def remote(request):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return httpx.Response(200, json={"errorId": 0, "balance": 1})

    keys = ProviderKeys(tmp_path)
    keys.update({"CapSolver": "fixture-key"})
    connection = httpx.AsyncClient(transport=httpx.MockTransport(remote))
    with TestClient(create_app(keys, client=connection), base_url=URL) as client:
        h = headers(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(client.post, "/api/check", headers=h, json={})
            try:
                assert started.wait(2)
                assert client.post("/api/check", headers=h, json={}).status_code == 429
            finally:
                release.set()
            assert first.result(timeout=3).status_code == 200
