"""Checkpoint-bound extension recovery through the real bounded downloader."""

import asyncio
import shutil
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from gflow_cli.api.native_extension import (
    NativeExtensionUnknownError,
    download_native_extension,
    new_extension_started,
)
from gflow_cli.api.transports import native_asset_download
from gflow_cli.api.transports.native_asset_lookup import NativeAsset

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def fixture(count=1):
    started = new_extension_started(P, M, count)
    records = [
        SimpleNamespace(
            project_id=P, media_id=m, workflow_id=w, video_url="https://expired.invalid"
        )
        for m, w in zip(started.media_ids, started.workflow_ids, strict=True)
    ]
    assets = [
        NativeAsset(
            row.media_id,
            P,
            row.workflow_id,
            "video",
            "https://flow-content.google/video/fresh?Signature=private",
            48,
            32,
        )
        for row in records
    ]
    return started, records, assets


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch", ["empty", "duplicate", "media", "workflow", "project", "missing-url"]
)
async def test_checkpoint_mismatch_never_downloads(tmp_path, mismatch):
    started, records, _ = fixture(2)
    if mismatch == "empty":
        records = []
    elif mismatch == "duplicate":
        records[1] = records[0]
    elif mismatch == "missing-url":
        records[0].video_url = None
    else:
        setattr(records[0], mismatch + "_id", M)
    client = SimpleNamespace(get_native_asset=AsyncMock())
    with pytest.raises(NativeExtensionUnknownError) as error:
        await download_native_extension(client, started, records, tmp_path)
    assert error.value.started == started and error.value.retryable is False
    client.get_native_asset.assert_not_awaited()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["project_id", "media_id", "workflow_id", "kind"])
async def test_fresh_identity_must_match_before_download(tmp_path, field):
    started, records, assets = fixture()
    client = SimpleNamespace(
        get_native_asset=AsyncMock(
            return_value=replace(assets[0], **{field: "image" if field == "kind" else M})
        )
    )
    with pytest.raises(NativeExtensionUnknownError):
        await download_native_extension(client, started, records, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_cancellation_preserves_checkpoint(tmp_path):
    started, records, _ = fixture()
    client = SimpleNamespace(get_native_asset=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await download_native_extension(client, started, records, tmp_path)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg tools required"
)
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["corrupt", "cancel"])
async def test_fresh_mp4_plural_partial_recovery_and_exclusive_write(
    tmp_path, monkeypatch, failure
):
    video = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=48x32:rate=24",
            "-t",
            "0.25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    body = video.read_bytes()
    video.unlink()
    started, records, assets = fixture(2)
    requests = []
    corrupt_second = True

    class CancelledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body[:12]
            raise asyncio.CancelledError

    def response(request):
        requests.append(request)
        assert request.url.host == "flow-content.google"
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert request.url.params["Signature"] == "private"
        if corrupt_second and len(requests) == 2 and failure == "cancel":
            return httpx.Response(
                200, headers={"content-type": "video/mp4"}, stream=CancelledStream()
            )
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=(b"wrong" if corrupt_second and len(requests) == 2 else body),
        )

    http_client = httpx.AsyncClient
    monkeypatch.setattr(
        native_asset_download.httpx,
        "AsyncClient",
        lambda **kwargs: http_client(transport=httpx.MockTransport(response), **kwargs),
    )
    client = SimpleNamespace(get_native_asset=AsyncMock(side_effect=assets))
    with pytest.raises(
        asyncio.CancelledError if failure == "cancel" else NativeExtensionUnknownError
    ) as error:
        await download_native_extension(client, started, records, tmp_path)
    if failure == "corrupt":
        assert error.value.started == started
    first = tmp_path / (started.media_ids[0] + ".mp4")
    assert first.read_bytes() == body and list(tmp_path.iterdir()) == [first]
    corrupt_second = False
    client.get_native_asset = AsyncMock(side_effect=assets)
    # Recovery may not replace an already validated sibling, even with identical bytes.
    with pytest.raises(NativeExtensionUnknownError):
        await download_native_extension(client, started, records, tmp_path)
    assert first.read_bytes() == body and list(tmp_path.iterdir()) == [first]
    recovered = tmp_path / "new-invocation-directory"
    client.get_native_asset = AsyncMock(side_effect=assets)
    outputs = await download_native_extension(client, started, records, recovered)
    assert tuple(item.media_id for item in outputs) == started.media_ids
    assert all((item.width, item.height) == (48, 32) for item in outputs)
    assert all(item.path.read_bytes() == body for item in outputs)
    assert len({item.sha256 for item in outputs}) == 1
