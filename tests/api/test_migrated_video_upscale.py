"""Unit tests for migrated_video_upscale (flow.google.com)."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.transports.migrated_video_upscale import upscale_video_migrated
from gflow_cli.errors import (
    TransportTimeoutError,
    UiSelectorDriftError,
    UpscaleUnavailableError,
    WireFormatError,
)

_DUMMY_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
_DUMMY_MP4_B64 = base64.b64encode(_DUMMY_MP4).decode("ascii")

_DUMMY_GIF = b"GIF89a" + b"\x00" * 32
_DUMMY_GIF_B64 = base64.b64encode(_DUMMY_GIF).decode("ascii")


@pytest.mark.asyncio
async def test_migrated_video_upscale_1080p_happy_path() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    tile = MagicMock()
    tile.click = AsyncMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    download_btn.click = AsyncMock()

    btn_1080p = MagicMock()
    btn_1080p.is_disabled = AsyncMock(return_value=False)
    btn_1080p.get_attribute = AsyncMock(return_value=None)
    btn_1080p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "data-media-id" in sel or "flow-grid-tile-container" in sel:
            return tile
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            return btn_1080p
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    eval_call_count = 0

    async def evaluate_mock(expr, *args):
        nonlocal eval_call_count
        if "window._videoCapturedBase64" in expr:
            eval_call_count += 1
            if eval_call_count >= 1:
                return _DUMMY_MP4_B64
        return None

    page.evaluate = AsyncMock(side_effect=evaluate_mock)

    result = await upscale_video_migrated(
        page,
        project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
        media_id="412832b1-3685-46f9-a5da-49c472d18a23",
        scale="1080p",
        timeout_s=5.0,
    )

    assert result == _DUMMY_MP4


@pytest.mark.asyncio
async def test_migrated_video_upscale_270p_gif() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    tile = MagicMock()
    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_270p = MagicMock()
    btn_270p.is_disabled = AsyncMock(return_value=False)
    btn_270p.get_attribute = AsyncMock(return_value=None)
    btn_270p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "270p" in sel:
            return btn_270p
        return tile

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    async def evaluate_mock(expr, *args):
        if "window._videoCapturedBase64" in expr:
            return _DUMMY_GIF_B64
        return None

    page.evaluate = AsyncMock(side_effect=evaluate_mock)

    result = await upscale_video_migrated(
        page,
        project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
        media_id="412832b1-3685-46f9-a5da-49c472d18a23",
        scale="270p",
        timeout_s=5.0,
    )

    assert result == _DUMMY_GIF


@pytest.mark.asyncio
async def test_migrated_video_upscale_invalid_scale() -> None:
    page = MagicMock()
    with pytest.raises(ValueError, match="Unsupported video upscale scale"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="4k",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_disabled_raises_unavailable() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    tile = MagicMock()
    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_1080p = MagicMock()
    btn_1080p.is_disabled = AsyncMock(return_value=True)
    btn_1080p.get_attribute = AsyncMock(return_value="true")

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            return btn_1080p
        return tile

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)

    with pytest.raises(UpscaleUnavailableError, match="1080p video option is not available"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_missing_menu_item_raises_drift() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            raise PlaywrightTimeoutError("timeout")
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)

    with pytest.raises(UiSelectorDriftError, match="menu item for 1080p was not found"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_timeout_raises_transport_timeout() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_1080p = MagicMock()
    btn_1080p.is_disabled = AsyncMock(return_value=False)
    btn_1080p.get_attribute = AsyncMock(return_value=None)
    btn_1080p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            return btn_1080p
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)

    with pytest.raises(TransportTimeoutError, match="Timed out waiting for 1080p video stream"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=0.01,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_missing_download_button() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))

    with pytest.raises(WireFormatError, match="Download button not found"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_invalid_magic_bytes() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_1080p = MagicMock()
    btn_1080p.is_disabled = AsyncMock(return_value=False)
    btn_1080p.get_attribute = AsyncMock(return_value=None)
    btn_1080p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            return btn_1080p
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    invalid_bytes_b64 = base64.b64encode(b"not an mp4 file").decode("ascii")
    page.evaluate = AsyncMock(return_value=invalid_bytes_b64)

    with pytest.raises(WireFormatError, match="not a valid MP4"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_invalid_magic_bytes_gif() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_270p = MagicMock()
    btn_270p.is_disabled = AsyncMock(return_value=False)
    btn_270p.get_attribute = AsyncMock(return_value=None)
    btn_270p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "270p" in sel:
            return btn_270p
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    invalid_bytes_b64 = base64.b64encode(b"not a gif file").decode("ascii")
    page.evaluate = AsyncMock(return_value=invalid_bytes_b64)

    with pytest.raises(WireFormatError, match="not a valid GIF"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="270p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_undecodable_base64() -> None:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.on = MagicMock()
    page.remove_listener = MagicMock()

    download_btn = MagicMock()
    download_btn.click = AsyncMock()
    btn_1080p = MagicMock()
    btn_1080p.is_disabled = AsyncMock(return_value=False)
    btn_1080p.get_attribute = AsyncMock(return_value=None)
    btn_1080p.click = AsyncMock()

    async def wait_for_selector(sel, **kwargs):
        if "download" in sel:
            return download_btn
        if "1080p" in sel:
            return btn_1080p
        return None

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    page.evaluate = AsyncMock(return_value="bad-base64-length-!")

    with pytest.raises(WireFormatError, match="undecodable stream data"):
        await upscale_video_migrated(
            page,
            project_id="9f4b4bce-b192-4687-a636-89d4e8c5ba98",
            media_id="412832b1-3685-46f9-a5da-49c472d18a23",
            scale="1080p",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_migrated_video_upscale_caps_encoded_payload_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gflow_cli.api.transports import migrated_video_upscale

    monkeypatch.setattr(migrated_video_upscale, "MAX_VIDEO_B64_LEN", 1, raising=False)
    with pytest.raises(WireFormatError, match="size cap"):
        await test_migrated_video_upscale_1080p_happy_path()


@pytest.mark.asyncio
@pytest.mark.parametrize("scale,data", [("720p", _DUMMY_MP4), ("270p", _DUMMY_GIF)])
async def test_browser_download_without_page_blob(tmp_path, scale, data):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    button = MagicMock()
    button.is_disabled = AsyncMock(return_value=False)
    button.get_attribute = AsyncMock(return_value=None)
    listeners = {}
    page.on.side_effect = lambda event, handler: listeners.update({event: handler})
    path = tmp_path / "browser-download"
    path.write_bytes(data)
    download = MagicMock()
    download.suggested_filename = "original.gif" if scale == "270p" else "original.mp4"
    download.failure = AsyncMock(return_value=None)
    download.path = AsyncMock(return_value=str(path))

    async def click():
        if "download" in listeners:
            listeners["download"](download)

    button.click = AsyncMock(side_effect=click)
    page.wait_for_selector = AsyncMock(return_value=button)
    result = await upscale_video_migrated(
        page, project_id="project", media_id="media", scale=scale, timeout_s=0.01
    )
    assert result == data
    page.remove_listener.assert_any_call("download", listeners["download"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["oversize", "wrong-magic", "failed"])
async def test_browser_download_rejects_unsafe_bytes(tmp_path, monkeypatch, mode):
    import gflow_cli.api.transports.migrated_video_upscale as module

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    button = MagicMock()
    button.is_disabled = AsyncMock(return_value=False)
    button.get_attribute = AsyncMock(return_value=None)
    listeners = {}
    page.on.side_effect = lambda event, handler: listeners.update({event: handler})
    path = tmp_path / "browser-download"
    path.write_bytes(_DUMMY_MP4 if mode != "wrong-magic" else b"not a video")
    if mode == "oversize":
        monkeypatch.setattr(module, "MAX_VIDEO_DOWNLOAD_BYTES", 16, raising=False)
    download = MagicMock()
    download.suggested_filename = "original.mp4"
    download.failure = AsyncMock(return_value="secret signed URL" if mode == "failed" else None)
    download.path = AsyncMock(return_value=str(path))

    async def click():
        if "download" in listeners:
            listeners["download"](download)

    button.click = AsyncMock(side_effect=click)
    page.wait_for_selector = AsyncMock(return_value=button)
    with pytest.raises(WireFormatError) as caught:
        await upscale_video_migrated(
            page, project_id="project", media_id="media", scale="720p", timeout_s=0.01
        )
    assert "secret signed URL" not in str(caught.value)


@pytest.mark.asyncio
async def test_stalled_browser_download_is_cancelled_on_timeout():
    import asyncio

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    button = MagicMock()
    button.is_disabled = AsyncMock(return_value=False)
    button.get_attribute = AsyncMock(return_value=None)
    listeners = {}
    page.on.side_effect = lambda event, handler: listeners.update({event: handler})
    cancelled = asyncio.Event()

    async def stalled():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    download = MagicMock()
    download.suggested_filename = "original.mp4"
    download.failure = AsyncMock(side_effect=stalled)

    async def click():
        if "download" in listeners:
            listeners["download"](download)

    button.click = AsyncMock(side_effect=click)
    page.wait_for_selector = AsyncMock(return_value=button)
    with pytest.raises(TransportTimeoutError):
        await upscale_video_migrated(
            page, project_id="project", media_id="media", scale="720p", timeout_s=0.01
        )
    assert cancelled.is_set()
    page.remove_listener.assert_any_call("download", listeners["download"])
