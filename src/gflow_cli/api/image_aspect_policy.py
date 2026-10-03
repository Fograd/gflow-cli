"""Local approximation of image Auto; never sends an invented Google Auto enum."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_RATIOS = (("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4), ("16:9", 16 / 9), ("9:16", 9 / 16))
_MAX_BYTES = 20 * 1024 * 1024
_MAX_PIXELS = 25_000_000


@dataclass(frozen=True)
class ImageAspectDecision:
    """Requested/resolved metadata for callers to retain in their output."""

    resolved_aspect: str
    requested_aspect: str = "auto"
    policy: str = "derived-first-reference-nearest-supported-v1"


def derive_aspect(width: int, height: int) -> ImageAspectDecision:
    """Nearest supported ratio by symmetric log distance; ties follow declared order.

    This deterministic local approximation preserves every exact supported ratio.
    It does not reproduce or claim knowledge of useapi/Google's internal algorithm.
    """
    if (
        type(width) is not int
        or type(height) is not int
        or not 0 < width <= _MAX_PIXELS
        or not 0 < height <= _MAX_PIXELS
    ):
        raise ValueError("Reference image dimensions must be positive bounded integers")
    ratio = width / height
    resolved = min(_RATIOS, key=lambda item: abs(math.log(ratio / item[1])))[0]
    return ImageAspectDecision(resolved)


def derive_aspect_from_file(path: Path) -> ImageAspectDecision:
    """Decode the caller-resolved first actual reference, without remote fetching.

    Callers own profile/project/path containment and first-reference ordering. A
    character entity alone cannot satisfy this policy. Error messages omit paths.
    """
    try:
        if not path.is_file() or path.stat().st_size > _MAX_BYTES:
            raise ValueError("First reference must be a local image of at most 20 MiB")
        with path.open("rb") as source:
            content = source.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise ValueError("First reference must be a local image of at most 20 MiB")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("First reference must be a valid PNG or JPEG image")
                width, height = image.size
                if width * height > _MAX_PIXELS:
                    raise ValueError("First reference exceeds the 25 megapixel decode limit")
                image.verify()
            # verify() checks structure; decoding checks truncated pixel streams too.
            with Image.open(BytesIO(content)) as image:
                image.load()
        return derive_aspect(width, height)
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("First reference must be a valid PNG or JPEG image") from exc
