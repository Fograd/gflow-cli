"""Callback status delivery must never buffer a recipient's response body."""

import asyncio
import socket
from unittest.mock import AsyncMock

import httpx
import pytest

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import deliver_callbacks
from gflow_cli.selfhost.store import Store


@pytest.mark.parametrize("status", [200, 500, 302])
def test_callback_body_never_read_and_stream_always_closed(tmp_path, monkeypatch, status):
    store = Store(tmp_path)
    store.submit("images", "pro1", {"replyUrl": "https://callbacks.example/hook"}, None)
    cfg = Settings(token="test", root=tmp_path, accounts={}, callbacks=("callbacks.example",))

    class Body(httpx.AsyncByteStream):
        reads = 0
        closed = 0

        async def __aiter__(self):
            self.reads += 1
            raise AssertionError("The unbounded response body must not be consumed")
            yield b""

        async def aclose(self):
            self.closed += 1

    body = Body()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, stream=body)

    client_class = httpx.AsyncClient
    configs = []

    def client(**kwargs):
        configs.append(kwargs)
        return client_class(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("gflow_cli.selfhost.runtime.httpx.AsyncClient", client)

    async def stop(_):
        raise asyncio.CancelledError()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.asyncio.sleep", stop)

    async def run():
        monkeypatch.setattr(
            asyncio.get_running_loop(),
            "getaddrinfo",
            AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]),
        )
        with pytest.raises(asyncio.CancelledError):
            await deliver_callbacks(cfg, store)

    asyncio.run(run())
    assert body.reads == 0
    assert body.closed == 1
    assert configs == [{"timeout": 10, "follow_redirects": False, "trust_env": False}]
    assert len(requests) == 1
    assert str(requests[0].url) == "https://8.8.8.8/hook"
    assert requests[0].headers["Host"] == "callbacks.example"
    assert requests[0].extensions["sni_hostname"] == "callbacks.example"
    with store.connection() as connection:
        callback = connection.execute("SELECT delivered,attempts FROM callbacks").fetchone()
    assert callback["delivered"] == int(200 <= status < 300)
    assert callback["attempts"] == 1
