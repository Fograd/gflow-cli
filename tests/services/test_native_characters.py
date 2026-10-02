import hashlib
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from gflow_cli.data.models import AssetKind
from gflow_cli.errors import ConfigurationError
from gflow_cli.services import native_characters as module

P = "11111111-1111-4111-8111-111111111111"
M = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"


def catalog(monkeypatch, tmp_path):
    path = tmp_path / "images with spaces ü.png"
    Image.new("RGB", (16, 16)).save(path)
    local = SimpleNamespace(
        path=path,
        storage_provider=None,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        bytes=path.stat().st_size,
    )
    asset = SimpleNamespace(
        profile_name="pro1", flow_project_id=P, kind=AssetKind.IMAGE, local_files=[local]
    )
    repo = MagicMock()
    repo.get_asset_by_flow_media_id.return_value = asset
    monkeypatch.setattr(module.DataStore, "open", lambda *a: nullcontext(None))
    monkeypatch.setattr(module, "DataRepository", lambda store: repo)
    return path, asset, repo


@pytest.mark.asyncio
async def test_second_uncatalogued_ref_prevents_browser(monkeypatch, tmp_path):
    _, asset, repo = catalog(monkeypatch, tmp_path)
    repo.get_asset_by_flow_media_id.side_effect = [asset, None]
    browser = MagicMock(side_effect=AssertionError("No browser"))
    monkeypatch.setattr(module, "FlowApiClient", browser)
    with pytest.raises(ConfigurationError):
        await module.create_character_from_images(
            profile="pro1",
            project_id=P,
            display_name="Name",
            image_reference_1=M,
            image_reference_2=N,
        )
    browser.assert_not_called()


@pytest.mark.parametrize("fault", ["hash", "kind", "project", "decode"])
@pytest.mark.asyncio
async def test_reference_faults_prevent_browser(monkeypatch, tmp_path, fault):
    path, asset, _ = catalog(monkeypatch, tmp_path)
    if fault == "hash":
        path.write_bytes(b"tampered")
    if fault == "kind":
        asset.kind = AssetKind.VIDEO
    if fault == "project":
        asset.flow_project_id = N
    if fault == "decode":
        path.write_bytes(b"not an image")
        asset.local_files[0].sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        asset.local_files[0].bytes = path.stat().st_size
    browser = MagicMock(side_effect=AssertionError("No browser"))
    monkeypatch.setattr(module, "FlowApiClient", browser)
    with pytest.raises(ConfigurationError):
        await module.create_character_from_images(
            profile="pro1", project_id=P, display_name="Name", image_reference_1=M
        )
    browser.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_proof_and_voice_canonicalization_reach_sdk(monkeypatch, tmp_path):
    catalog(monkeypatch, tmp_path)
    sdk = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=sdk)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "FlowApiClient", lambda **kw: context)
    await module.create_character_from_images(
        profile="pro1", project_id=P, display_name="Name", image_reference_1=M, voice="cHaRoN"
    )
    assert sdk.create_character_from_images.await_args.kwargs["image_reference_confirmed"] is True
    assert sdk.create_character_from_images.await_args.kwargs["voice"] == "Charon"


@pytest.mark.asyncio
async def test_header_valid_truncated_jpeg_is_refused_before_browser(monkeypatch, tmp_path):
    path, asset, _ = catalog(monkeypatch, tmp_path)
    Image.new("RGB", (128, 128), "blue").save(path, format="JPEG")
    path.write_bytes(path.read_bytes()[:-20])
    # Pillow verify accepts this header, while pixel decoding fails.
    with Image.open(path) as image:
        image.verify()
    local = asset.local_files[0]
    local.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    local.bytes = path.stat().st_size
    browser = MagicMock(side_effect=AssertionError("No browser"))
    monkeypatch.setattr(module, "FlowApiClient", browser)
    with pytest.raises(ConfigurationError):
        await module.create_character_from_images(
            profile="pro1", project_id=P, display_name="Name", image_reference_1=M
        )
    browser.assert_not_called()
