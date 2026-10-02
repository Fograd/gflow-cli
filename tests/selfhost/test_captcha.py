import httpx
import pytest

from gflow_cli.selfhost.captcha import ProviderKeys, Solver, SolverError


def test_keys_are_private_masked_and_atomic(tmp_path):
    keys = ProviderKeys(tmp_path)
    keys.update({"CapSolver": "secret-do-not-display"})
    assert "secret-do-not-display" not in str(keys.public())
    assert keys.get("CapSolver") == "secret-do-not-display"
    assert keys.path.stat().st_mode & 0o777 == 0o600
    keys.update({"CapSolver": ""})
    assert keys.public() == {}
    with pytest.raises(ValueError):
        keys.update({"other": "key"})


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["CapSolver", "2Captcha"])
async def test_enterprise_task_and_solution(provider):
    calls = []

    def handler(request):
        import json

        data = json.loads(request.content)
        calls.append(data)
        if request.url.path == "/createTask":
            return httpx.Response(200, json={"errorId": 0, "taskId": 123})
        return httpx.Response(
            200,
            json={"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "t" * 100}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Solver(client=client, poll_interval=0).solve(
            provider, "key", "https://flow.google.com/project/test", "sitekey", "IMAGE_GENERATION"
        )
    assert result.token == "t" * 100
    task = calls[0]["task"]
    if provider == "2Captcha":
        assert task["type"] == "RecaptchaV3TaskProxyless"
        assert task["isEnterprise"] is True
        assert task["pageAction"] == "IMAGE_GENERATION"
    else:
        assert task["type"] == "ReCaptchaV3EnterpriseTaskProxyLess"
        assert task["pageAction"] == "IMAGE_GENERATION"


@pytest.mark.asyncio
async def test_provider_failure_does_not_leak_key_or_body():
    def handler(request):
        return httpx.Response(200, json={"errorId": 1, "errorDescription": "secret-key-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SolverError) as exc:
            await Solver(client=client).solve(
                "CapSolver",
                "secret-key",
                "https://flow.google.com/project/test",
                "sitekey",
                "IMAGE_GENERATION",
            )
    assert "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_timeout_is_bounded_without_resubmitting_task():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"errorId": 0, "taskId": 12, "status": "processing"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SolverError):
            await Solver(client=client, timeout=0.03, poll_interval=0.01).solve(
                "CapSolver",
                "key",
                "https://flow.google.com/project/test",
                "sitekey",
                "IMAGE_GENERATION",
            )
    assert calls.count("/createTask") == 1


def test_keys_preserve_other_secrets_and_reject_shell_metacharacters(tmp_path):
    keys = ProviderKeys(tmp_path)
    keys.path.write_text("UNRELATED=value\nGFLOW_DAEMON_TOKEN=existing\n")
    keys.update({"CapSolver": "safe_key-123"})
    assert "UNRELATED=value\nGFLOW_DAEMON_TOKEN=existing\n" in keys.path.read_text()
    before = keys.path.read_bytes()
    with pytest.raises(ValueError):
        keys.update({"CapSolver": "$(unsafe)"})
    assert keys.path.read_bytes() == before


def test_provider_routes_are_masked_and_authenticated(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gflow_cli.selfhost import captcha_routes
    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.server import create_app

    keys = ProviderKeys(tmp_path / "private")
    monkeypatch.setattr(captcha_routes, "provider_keys", lambda: keys)
    app = create_app(
        Settings(token="test", root=tmp_path / "queue", accounts={}), start_workers=False
    )
    with TestClient(app) as client:
        url = "/v1/google-flow/accounts/captcha-providers"
        assert client.get(url).status_code == 401
        r = client.post(
            url, json={"CapSolver": "private-key"}, headers={"Authorization": "Bearer test"}
        )
        assert r.status_code == 200
        assert "private-key" not in r.text
        assert client.get(url, headers={"Authorization": "Bearer test"}).json() == {
            "CapSolver": "***configured***"
        }


def test_supplied_token_never_remains_in_public_payload(tmp_path):
    from gflow_cli.selfhost.captcha_routes import prepare_image_controls

    token = "secret-token-" * 10
    payload = {"captchaToken": token, "prompt": "image"}
    prepare_image_controls(payload, tmp_path)
    assert token not in str(payload)
    from pathlib import Path

    path = Path(payload["captchaSecret"])
    assert path.read_text() == token
    assert path.stat().st_mode & 0o777 == 0o600


async def test_solver_stream_limit_stops_before_full_response():
    class Stream(httpx.AsyncByteStream):
        consumed = 0

        async def __aiter__(self):
            for _ in range(100):
                self.consumed += 1
                yield b"x" * 8192

    stream = Stream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    ) as client:
        with pytest.raises(SolverError, match="exceeded"):
            await Solver._post(client, "CapSolver", "/createTask", {})
    assert stream.consumed == 9


async def test_capsolver_balance_returns_number_only():
    def handler(request):
        import json

        assert request.url.host == "api.capsolver.com" and request.url.path == "/getBalance"
        assert json.loads(request.content) == {"clientKey": "private-key"}
        return httpx.Response(
            200, json={"errorId": 0, "balance": 3.25, "packages": ["private-package"]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await Solver(client=client).balance("private-key") == 3.25


@pytest.mark.parametrize("balance", [True, "12.5", -1, None, float("inf"), float("nan")])
async def test_capsolver_balance_rejects_malformed_numbers(balance):
    import json

    def handler(request):
        return httpx.Response(200, content=json.dumps({"errorId": 0, "balance": balance}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SolverError, match="invalid balance"):
            await Solver(client=client).balance("private-key")


@pytest.mark.parametrize(
    "status,body",
    [
        (200, b'{"errorId":1,"errorDescription":"private-key"}'),
        (200, b"private-key malformed"),
        (302, b"private-key redirect"),
        (200, b"private-key" * 10000),
    ],
)
async def test_balance_errors_redacted_and_bounded(status, body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))
    ) as client:
        with pytest.raises(SolverError) as caught:
            await Solver(client=client).balance("private-key")
        assert "private-key" not in str(caught.value)


async def test_balance_does_not_redirect_even_injected_client_allows_it():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://untrusted.example/key"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(SolverError):
            await Solver(client=client).balance("private-key")
    assert calls == ["https://api.capsolver.com/getBalance"]
