from pathlib import Path

import pytest
from PIL import Image

from gflow_cli.api.image_aspect_policy import derive_aspect, derive_aspect_from_file


@pytest.mark.parametrize(
    "ratio,width,height",
    [
        ("16:9", 1600, 900),
        ("4:3", 1200, 900),
        ("1:1", 900, 900),
        ("3:4", 900, 1200),
        ("9:16", 900, 1600),
    ],
)
def test_exact_supported_ratios(ratio: str, width: int, height: int) -> None:
    decision = derive_aspect(width, height)
    assert decision.resolved_aspect == ratio
    assert decision.requested_aspect == "auto"
    assert decision.policy == "derived-first-reference-nearest-supported-v1"


def test_scale_and_orientation_are_symmetric() -> None:
    assert derive_aspect(1376, 768).resolved_aspect == "16:9"
    assert derive_aspect(768, 1376).resolved_aspect == "9:16"
    assert derive_aspect(13760, 7680) == derive_aspect(1376, 768)
    assert derive_aspect(1000, 900).resolved_aspect == "1:1"


@pytest.mark.parametrize("width,height", [(True, 1), (1, False), (0, 1), (1, -2), (1 << 1024, 1)])
def test_invalid_dimensions_fail_closed(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        derive_aspect(width, height)


def test_decodes_first_reference(tmp_path: Path) -> None:
    image = tmp_path / "first.png"
    Image.new("RGB", (640, 480)).save(image)
    assert derive_aspect_from_file(image).resolved_aspect == "4:3"


def test_corrupt_reference_has_safe_error(tmp_path: Path) -> None:
    image = tmp_path / "private-name.png"
    image.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="valid PNG or JPEG") as exc:
        derive_aspect_from_file(image)
    assert str(image) not in str(exc.value)


def test_unsupported_format_refused(tmp_path: Path) -> None:
    image = tmp_path / "image.gif"
    Image.new("RGB", (10, 10)).save(image)
    with pytest.raises(ValueError, match="PNG or JPEG"):
        derive_aspect_from_file(image)


def test_oversized_reference_refused_before_decode(tmp_path: Path) -> None:
    image = tmp_path / "large.png"
    with image.open("wb") as handle:
        handle.truncate(20 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="20 MiB"):
        derive_aspect_from_file(image)


def test_missing_reference_has_safe_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="local image") as exc:
        derive_aspect_from_file(tmp_path / "missing-private.png")
    assert "missing-private" not in str(exc.value)


def test_pixel_bound_applies_before_decode(tmp_path: Path) -> None:
    image = tmp_path / "dimensions.png"
    Image.new("1", (5001, 5000)).save(image)
    with pytest.raises(ValueError, match="25 megapixel"):
        derive_aspect_from_file(image)


def test_truncated_pixels_fail_closed(tmp_path: Path) -> None:
    image = tmp_path / "truncated.jpg"
    Image.new("RGB", (128, 128)).save(image)
    image.write_bytes(image.read_bytes()[:-50])
    with pytest.raises(ValueError, match="valid PNG or JPEG"):
        derive_aspect_from_file(image)
