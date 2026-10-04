"""Private image caching cannot replace scoped managed assets or relax raw downloads."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.selfhost import native_worker
from gflow_cli.selfhost.config import MAX_ASSET
from gflow_cli.selfhost.store import Store

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"


def test_cache_insert_and_same_scope_preserve_original_path(tmp_path):
    store = Store(tmp_path)
    assert store.asset_cache_if_scope(M, "pro1", P, "/original.png", "image/png") is True
    before = store.asset_get(M)
    assert store.asset_cache_if_scope(M, "pro1", P, "/replacement.png", "image/png") is False
    assert store.asset_get(M) == before
    assert Store(tmp_path).asset_get(M) == before


@pytest.mark.parametrize(
    "profile,project,mime",
    [("pro2", P, "image/png"), ("pro1", M, "image/png"), ("pro1", P, "image/jpeg")],
)
def test_cache_conflicting_scope_never_replaces_asset(tmp_path, profile, project, mime):
    store = Store(tmp_path)
    store.asset(M, "pro1", P, "/original.png", "image/png")
    before = store.asset_get(M)
    with pytest.raises(ValueError, match="scope conflict"):
        store.asset_cache_if_scope(M, profile, project, "/replacement.png", mime)
    assert store.asset_get(M) == before


def test_concurrent_cache_insert_has_one_winner_without_path_replacement(tmp_path):
    store = Store(tmp_path)

    def insert(index):
        return index, store.asset_cache_if_scope(M, "pro1", P, f"/{index}.png", "image/png")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(insert, range(8)))
    winners = [index for index, inserted in results if inserted]
    assert len(winners) == 1
    assert store.asset_get(M)["path"] == f"/{winners[0]}.png"


@pytest.fixture
def worker(monkeypatch, tmp_path):
    asset = SimpleNamespace(kind="image")
    client = SimpleNamespace(get_native_asset=AsyncMock(return_value=asset))
    context = AsyncMock()
    context.__aenter__.return_value = client
    constructor = Mock(return_value=context)
    monkeypatch.setattr(native_worker, "FlowApiClient", constructor)
    monkeypatch.setattr(
        native_worker, "get_settings", lambda: SimpleNamespace(flow_host="flow.google")
    )
    monkeypatch.setattr(native_worker.auth, "profile_dir", lambda profile: tmp_path / profile)
    downloaded = SimpleNamespace(
        media_id=M,
        project_id=P,
        kind="image",
        path=tmp_path / "image.png",
        mime_type="image/png",
        bytes=42,
    )
    download = AsyncMock(return_value=downloaded)
    monkeypatch.setattr("gflow_cli.api.transports.native_asset_download.download_asset", download)
    return client, asset, download, tmp_path


@pytest.mark.asyncio
async def test_private_image_cache_uses_fresh_lookup_and_explicit_size_cap(worker):
    client, asset, download, output = worker
    result = await native_worker.execute(
        "asset-cache-image",
        "fixture",
        {"project_id": P, "media_id": M, "output_dir": str(output)},
    )
    client.get_native_asset.assert_awaited_once_with(P, M)
    download.assert_awaited_once_with(asset, output, max_bytes=MAX_ASSET)
    assert result == {
        "status": "ok",
        "mediaGenerationId": M,
        "projectId": P,
        "kind": "image",
        "path": str(output / "image.png"),
        "mimeType": "image/png",
        "bytes": 42,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["video", "audio", "unknown"])
async def test_private_image_cache_refuses_wrong_kind_before_download(worker, kind):
    client, asset, download, output = worker
    asset.kind = kind
    with pytest.raises(ValueError, match="wrong media kind"):
        await native_worker.execute(
            "asset-cache-image",
            "fixture",
            {"project_id": P, "media_id": M, "output_dir": str(output)},
        )
    client.get_native_asset.assert_awaited_once_with(P, M)
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_raw_download_accepts_validated_image(worker):
    client, asset, download, output = worker
    result = await native_worker.execute(
        "asset-download",
        "fixture",
        {"project_id": P, "media_id": M, "output_dir": str(output)},
    )
    client.get_native_asset.assert_awaited_once_with(P, M)
    download.assert_awaited_once_with(asset, output, max_bytes=256 * 1024 * 1024)
    assert result["kind"] == "image" and result["mimeType"] == "image/png"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["audio", "unknown"])
async def test_public_raw_download_refuses_unverified_kind(worker, kind):
    client, asset, download, output = worker
    asset.kind = kind
    with pytest.raises(ValueError, match="wrong media kind"):
        await native_worker.execute(
            "asset-download",
            "fixture",
            {"project_id": P, "media_id": M, "output_dir": str(output)},
        )
    download.assert_not_awaited()
