"""Native signed downloads validate content and do not forward browser cookies."""

import io

import httpx
import pytest
from PIL import Image

from gflow_cli.api.transports.native_asset_download import download_asset
from gflow_cli.api.transports.native_asset_lookup import NativeAsset

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
URL = "https://flow-content.google/image/owned?Signature=private"


def png():
    data = io.BytesIO()
    Image.new("RGB", (48, 32)).save(data, format="PNG")
    return data.getvalue()


def asset():
    return NativeAsset(M, P, W, "image", URL, 48, 32)


async def run(tmp_path, response, **kwargs):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        return await download_asset(asset(), tmp_path, http=client, **kwargs)


@pytest.mark.asyncio
async def test_image_content_dimensions_and_exclusive_write(tmp_path):
    body = png()
    result = await run(
        tmp_path, httpx.Response(200, headers={"content-type": "image/png"}, content=body)
    )
    assert result.path.read_bytes() == body
    assert result.bytes == len(body)
    assert result.path.name == M + ".png"
    with pytest.raises(FileExistsError):
        await run(
            tmp_path, httpx.Response(200, headers={"content-type": "image/png"}, content=body)
        )
    assert result.path.read_bytes() == body
    assert list(tmp_path.iterdir()) == [result.path]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "http://localhost/private"}),
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>no</html>"),
        httpx.Response(200, headers={"content-type": "image/png"}, content=b"wrong"),
        httpx.Response(200, headers={"content-type": "image/png"}, content=b""),
    ],
)
async def test_refused_content_leaves_no_file_or_url_error(tmp_path, response):
    with pytest.raises(ValueError) as exc:
        await run(tmp_path, response)
    assert "Signature" not in str(exc.value)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_byte_budget(tmp_path):
    with pytest.raises(ValueError):
        await run(
            tmp_path,
            httpx.Response(200, headers={"content-type": "image/png"}, content=png()),
            max_bytes=10,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_dimension_mismatch(tmp_path):
    data = io.BytesIO()
    Image.new("RGB", (32, 48)).save(data, format="PNG")
    with pytest.raises(ValueError):
        await run(
            tmp_path,
            httpx.Response(200, headers={"content-type": "image/png"}, content=data.getvalue()),
        )
    assert not list(tmp_path.iterdir())


def test_protected_url_excluded_from_repr():
    assert "Signature" not in repr(asset())


@pytest.mark.asyncio
async def test_httpx_info_logger_cannot_emit_protected_url(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="httpx")
    await run(tmp_path, httpx.Response(200, headers={"content-type": "image/png"}, content=png()))
    logging.getLogger("httpx").info("ordinary-request-after-private-scope")
    assert "Signature" not in caplog.text
    assert "ordinary-request-after-private-scope" in caplog.text


@pytest.mark.asyncio
async def test_available_metadata_byte_count_is_required(tmp_path):
    from dataclasses import replace

    expected = replace(asset(), size_bytes=1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "image/png"}, content=png()
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="byte count"):
            await download_asset(expected, tmp_path, http=client)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_video_absent_metadata_dimensions_are_measured_from_mp4(tmp_path, monkeypatch):
    import json

    from gflow_cli.api.transports import native_asset_download as module

    class Probe:
        returncode = 0

        async def communicate(self):
            return json.dumps({"streams": [{"width": 1280, "height": 720}]}).encode(), b""

    async def spawn(*args, **kwargs):
        return Probe()

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    video = NativeAsset(M, P, W, "video", URL.replace("/image/", "/video/"), None, None)
    body = b"\x00\x00\x00\x18ftypisom" + b"mp4-body"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "video/mp4"}, content=body)
        )
    ) as client:
        result = await download_asset(video, tmp_path, http=client)
    assert (result.width, result.height) == (1280, 720)
    assert result.path.read_bytes() == body
