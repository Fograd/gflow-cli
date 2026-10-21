"""Normalize WebP references and safely stage local upload bytes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from gflow_cli.selfhost.config import MAX_ASSET


@dataclass(frozen=True)
class PreparedImageUpload:
    data: bytes = field(repr=False)
    content_type: str
    source_content_type: str
    converted: bool


def prepare_image_upload(
    data: object, content_type: str, *, max_bytes: int = MAX_ASSET
) -> PreparedImageUpload:
    """Keep supported bytes unchanged; fully verify/decode one-frame WebP to PNG.

    Google native uploaded-image binding accepts PNG/JPEG. Conversion preserves
    pixels and alpha, drops optional metadata, and enforces both input/output caps.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ASSET:
        raise ValueError("Invalid image upload byte limit")
    if not isinstance(data, bytes) or not data or len(data) > max_bytes:
        raise ValueError("Image exceeds upload byte limit")
    if content_type in ("image/png", "image/jpeg"):
        signature = b"\x89PNG\r\n\x1a\n" if content_type == "image/png" else b"\xff\xd8\xff"
        if not data.startswith(signature):
            raise ValueError("Image signature does not match content type")
        return PreparedImageUpload(data, content_type, content_type, False)
    if content_type != "image/webp":
        raise ValueError("Image upload requires PNG, JPEG or WebP")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format != "WEBP":
                raise ValueError("Image signature does not match content type")
            if getattr(source, "is_animated", False):
                raise ValueError("animated WebP uploads are unsupported")
            source.verify()
        with Image.open(BytesIO(data)) as source:
            source.load()
            pixels = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            output = BytesIO()
            pixels.save(output, format="PNG")
            converted = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid WebP upload image") from exc
    if len(converted) > max_bytes:
        raise ValueError("Converted image exceeds upload byte limit")
    return PreparedImageUpload(converted, "image/png", content_type, True)


def stage_upload_bytes(path: Path, data: bytes | bytearray) -> None:
    """Publish complete bytes atomically; never truncate an already-shared reference."""
    digest = hashlib.sha256(data).digest()
    try:
        if (
            path.stat().st_size == len(data)
            and hashlib.sha256(path.read_bytes()).digest() == digest
        ):
            return
    except FileNotFoundError:
        pass
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            if output.write(data) != len(data):
                raise OSError("Incomplete upload cache write")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
