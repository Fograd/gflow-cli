import asyncio

import pytest

from gflow_cli.selfhost.native_asset_response import EphemeralFileResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_response_cleanup_on_send_failure(tmp_path, failure):
    directory = tmp_path / "unique"
    directory.mkdir()
    path = directory / "clip.mp4"
    path.write_bytes(b"video")
    response = EphemeralFileResponse(path, directory)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        raise failure()

    with pytest.raises(failure):
        await response(
            {"type": "http", "method": "GET", "headers": [], "asgi": {"spec_version": "2.4"}},
            receive,
            send,
        )
    assert not directory.exists()
