import pytest
from PIL import Image

from gflow_cli.api.image import Aspect, ImageRef
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.image_aspect import aspect_decision_metadata, resolve_image_aspect


def test_auto_uses_first_local_reference_not_later_orientation(tmp_path):
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGB", (160, 90)).save(first)
    Image.new("RGB", (90, 160)).save(second)
    aspect, decision = resolve_image_aspect("auto", (first, second))
    assert aspect is Aspect.LANDSCAPE
    assert aspect_decision_metadata(decision) == {
        "requestedAspectRatio": "auto",
        "resolvedAspectRatio": "16:9",
        "aspectPolicy": "derived-first-reference-nearest-supported-v1",
    }


def test_explicit_aspect_does_not_decode_or_require_references():
    aspect, decision = resolve_image_aspect("1:1", ())
    assert aspect is Aspect.SQUARE
    assert aspect_decision_metadata(decision) == {}


@pytest.mark.parametrize("refs", [(), (ImageRef("00000000-0000-4000-8000-000000000001"),)])
def test_auto_unresolved_uuid_or_text_only_refuses(refs):
    with pytest.raises(ConfigurationError):
        resolve_image_aspect("auto", refs)


def test_auto_never_skips_first_uuid_for_later_file(tmp_path):
    image = tmp_path / "second.png"
    Image.new("RGB", (10, 10)).save(image)
    with pytest.raises(ConfigurationError):
        resolve_image_aspect("auto", (ImageRef("uuid"), image))


def test_corrupt_first_image_error_omits_private_path(tmp_path):
    path = tmp_path / "private-invalid.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ConfigurationError) as error:
        resolve_image_aspect("auto", (path,))
    assert str(path) not in str(error.value)
