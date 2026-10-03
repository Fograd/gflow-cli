"""Bounded unauthenticated reads of freshly verified protected media URLs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from gflow_cli.api.transports.native_asset_lookup import NativeAsset, media_url
from gflow_cli.api.transports.native_voices import validate_identifier

_signed_request_active: ContextVar[bool] = ContextVar("gflow_signed_request_active", default=False)


class _PrivateRequestFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _signed_request_active.get()


# Per-task filtering, never a process-wide temporary level change. HTTPX otherwise
# logs the complete bearer URL at INFO even when our own events contain no URL.
logging.getLogger("httpx").addFilter(_PrivateRequestFilter())


@contextmanager
def _quiet_signed_request() -> Generator[None, None, None]:
    token = _signed_request_active.set(True)
    try:
        yield
    finally:
        _signed_request_active.reset(token)


@dataclass(frozen=True)
class DownloadedNativeAsset:
    media_id: str
    project_id: str
    workflow_id: str
    kind: str
    path: Path
    bytes: int
    sha256: str
    mime_type: str
    width: int
    height: int


def _image(path: Path, asset: NativeAsset, mime: str) -> str:
    try:
        with Image.open(path) as image:
            if image.format not in ("PNG", "JPEG"):
                raise ValueError
            expected = "image/png" if image.format == "PNG" else "image/jpeg"
            if mime != expected or image.size != (asset.width, asset.height):
                raise ValueError
            image.verify()
        with Image.open(path) as decoded:
            decoded.load()
        with Image.open(path) as image:
            return ".png" if image.format == "PNG" else ".jpg"
    except Exception:
        raise ValueError("Native image bytes, type or dimensions do not match metadata") from None


async def _video(path: Path, asset: NativeAsset, mime: str) -> str:
    with path.open("rb") as stream:
        head = stream.read(12)
    if mime != "video/mp4" or len(head) < 12 or head[4:8] != b"ftyp":
        raise ValueError("Native video response is not an MP4")
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise ValueError("Native video content validation requires ffprobe") from None
    try:
        async with asyncio.timeout(15):
            output, _ = await process.communicate()
        data: Any = json.loads(output)
        streams = data.get("streams", [])
        if (
            process.returncode
            or len(streams) != 1
            or (streams[0].get("width"), streams[0].get("height")) != (asset.width, asset.height)
        ):
            raise ValueError
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ValueError("Native video bytes or dimensions do not match metadata") from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return ".mp4"


async def download_asset(
    asset: NativeAsset,
    out_dir: Path,
    *,
    http: httpx.AsyncClient | None = None,
    max_bytes: int = 256 * 1024 * 1024,
) -> DownloadedNativeAsset:
    """Fetch exact fresh URL without browser cookies, redirects or silent transcodes.

    Caller may provide an HTTP client for tests, but each request explicitly disables
    redirects. No signed URL appears in the durable result or diagnostic errors.
    """
    validate_identifier(asset.media_id)
    media_url(asset.url, asset.kind)
    if asset.kind == "image":
        max_bytes = min(max_bytes, 32 * 1024 * 1024)
    if max_bytes <= 0 or max_bytes > 256 * 1024 * 1024:
        raise ValueError("Native download byte budget must be 1 to 256 MiB")
    if http is None:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            return await download_asset(asset, out_dir, http=client, max_bytes=max_bytes)
    out_dir.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        async with asyncio.timeout(90):
            with tempfile.NamedTemporaryFile(
                dir=out_dir, prefix=".gflow-native-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                size = 0
                digest = hashlib.sha256()
                with _quiet_signed_request():
                    try:
                        async with http.stream(
                            "GET", asset.url, follow_redirects=False, timeout=30
                        ) as response:
                            if response.status_code != 200:
                                raise ValueError(
                                    "Native signed media request failed HTTP "
                                    + str(response.status_code)
                                )
                            mime = (
                                response.headers.get("content-type", "")
                                .split(";")[0]
                                .lower()
                                .strip()
                            )
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > max_bytes:
                                    raise ValueError(
                                        "Native media exceeds the download byte budget"
                                    )
                                stream.write(chunk)
                                digest.update(chunk)
                    except httpx.HTTPError:
                        raise ValueError("Native signed media request failed") from None
            if asset.size_bytes is not None and size != asset.size_bytes:
                raise ValueError("Native media byte count does not match its metadata")
            if not size:
                raise ValueError("Native media response is empty")
            extension = (
                _image(temporary, asset, mime)
                if asset.kind == "image"
                else await _video(temporary, asset, mime)
            )
            destination = out_dir / (asset.media_id + extension)
            os.link(temporary, destination)
            return DownloadedNativeAsset(
                asset.media_id,
                asset.project_id,
                asset.workflow_id,
                asset.kind,
                destination,
                size,
                digest.hexdigest(),
                mime,
                asset.width,
                asset.height,
            )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
