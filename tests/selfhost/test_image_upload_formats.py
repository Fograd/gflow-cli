"""WebP input is converted to native-supported PNG with truthful MIME and byte limits."""

from io import BytesIO

import pytest
from PIL import Image

from gflow_cli.selfhost.image_upload import prepare_image_upload


def webp(mode="RGB"):
    image = Image.new(mode, (8, 6), (10, 20, 30, 70) if mode == "RGBA" else (10, 20, 30))
    output = BytesIO()
    image.save(output, format="WEBP", lossless=True)
    return output.getvalue()


def test_webp_conversion_preserves_size_and_transparency_with_explicit_mime():
    original = webp("RGBA")
    result = prepare_image_upload(original, "image/webp")
    assert result.content_type == "image/png"
    assert result.source_content_type == "image/webp" and result.converted is True
    assert result.data.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(result.data)) as image:
        assert image.size == (8, 6)
        assert image.convert("RGBA").getpixel((0, 0)) == (10, 20, 30, 70)
    assert "RIFF" not in repr(result)


def test_opaque_webp_is_decoded_as_rgb_png():
    result = prepare_image_upload(webp(), "image/webp")
    with Image.open(BytesIO(result.data)) as image:
        assert image.format == "PNG" and image.mode == "RGB"


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"not-an-image", "image/webp"),
        (webp()[:20], "image/webp"),
        (webp(), "image/png"),
        (webp(), "video/mp4"),
    ],
)
def test_invalid_or_mismatched_upload_does_not_return_converted_bytes(data, mime):
    with pytest.raises(ValueError):
        prepare_image_upload(data, mime)


def test_animated_webp_is_refused_without_silent_frame_loss():
    output = BytesIO()
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(ValueError, match="animated"):
        prepare_image_upload(output.getvalue(), "image/webp")


def test_upload_input_and_converted_output_are_both_capped():
    original = webp()
    with pytest.raises(ValueError, match="limit"):
        prepare_image_upload(original, "image/webp", max_bytes=len(original) - 1)
    # Valid compressed WebP can expand to a PNG exceeding the transport byte cap.
    image = Image.frombytes(
        "RGB", (64, 64), bytes((i * 17 + i // 7) % 256 for i in range(64 * 64 * 3))
    )
    output = BytesIO()
    image.save(output, format="WEBP", quality=5)
    original = output.getvalue()
    with pytest.raises(ValueError, match="limit"):
        prepare_image_upload(original, "image/webp", max_bytes=len(original) + 1)


@pytest.mark.parametrize("format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_existing_native_formats_keep_exact_bytes_and_content_type(format, mime):
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, format=format)
    data = output.getvalue()
    result = prepare_image_upload(data, mime)
    assert result.data == data and result.content_type == result.source_content_type == mime
    assert result.converted is False
