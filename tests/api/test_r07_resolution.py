"""R07 owned source measurement and shared promotion completion regressions."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api import native_video_upscale as module
from gflow_cli.api.transports.native_asset_lookup import NativeAsset
from tests.api.test_native_video_upscale import MEDIA, PROJECT, WORKFLOW


def owned(monkeypatch):
    monkeypatch.setattr(
        module,
        "parse_media_snapshot",
        lambda *a: {"media": [{"media_id": MEDIA, "workflow_id": WORKFLOW, "kind": "video"}]},
    )
    monkeypatch.setattr(
        module,
        "project_media",
        lambda *a: [
            {
                "workflow_id": WORKFLOW,
                "project_id": PROJECT,
                "archived": False,
                "batch_media_ids": [MEDIA],
            }
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dims", [[None, None], [None, None, [1]], [640, 360]])
async def test_source_measures_only_explicitly_absent_dimensions(monkeypatch, tmp_path, dims):
    owned(monkeypatch)
    uploaded = [None, None, "https://flow-content.google/video/test.mp4"]
    row = [MEDIA, PROJECT, WORKFLOW, None, None, None, None, [None, dims, None, None, uploaded]]
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "native_rpc", AsyncMock(return_value=row))
    paths = []

    async def download(asset, directory):
        assert (asset.media_id, asset.project_id, asset.workflow_id) == (MEDIA, PROJECT, WORKFLOW)
        paths.append(directory)
        return SimpleNamespace(width=640, height=360)

    monkeypatch.setattr("gflow_cli.api.transports.native_asset_download.download_asset", download)
    result = await module.read_promotion_source(Mock(), project_id=PROJECT, media_id=MEDIA)
    assert (result.width, result.height) == (640, 360)
    assert len(paths) == (1 if dims[:2] == [None, None] else 0)
    assert all(not path.exists() for path in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "low-resolution",
        "wrong-aspect",
        "foreign-media",
        "foreign-project",
        "foreign-workflow",
        "image",
        "lookup-failure",
    ],
)
async def test_sdk_wait_refuses_invalid_output_with_handles(monkeypatch, fault):
    started = module.new_promotion_started(PROJECT, MEDIA, WORKFLOW, "720p")
    monkeypatch.setattr(module, "wait_native_extension", AsyncMock(return_value=("poll-record",)))
    asset = NativeAsset(
        started.media_ids[0],
        PROJECT,
        WORKFLOW,
        "video",
        "https://flow-content.google/video/test.mp4",
        1280,
        720,
    )
    changes = {
        "low-resolution": {"width": 640, "height": 360},
        "wrong-aspect": {"width": 720, "height": 720},
        "foreign-media": {"media_id": MEDIA},
        "foreign-project": {"project_id": MEDIA},
        "foreign-workflow": {"workflow_id": MEDIA},
        "image": {"kind": "image"},
    }
    lookup = AsyncMock(return_value=replace(asset, **changes.get(fault, {})))
    if fault == "lookup-failure":
        lookup.side_effect = ValueError("private signed URL")
    client = SimpleNamespace(get_native_asset=lookup)
    with pytest.raises(module.NativeVideoUpscaleUnknownError) as caught:
        await module.wait_native_promotion(client, started)
    assert caught.value.started == started
    assert "private signed URL" not in str(caught.value)
    assert lookup.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "width", "height"), [("720p", 1280, 720), ("1080p", 1920, 1080), ("4k", 3840, 2160)]
)
async def test_sdk_wait_accepts_exact_target(monkeypatch, target, width, height):
    started = module.new_promotion_started(PROJECT, MEDIA, WORKFLOW, target)
    monkeypatch.setattr(module, "wait_native_extension", AsyncMock(return_value=("poll-record",)))
    client = SimpleNamespace(
        get_native_asset=AsyncMock(
            return_value=NativeAsset(
                started.media_ids[0],
                PROJECT,
                WORKFLOW,
                "video",
                "https://flow-content.google/video/test.mp4",
                width,
                height,
            )
        )
    )
    assert await module.wait_native_promotion(client, started) == ("poll-record",)
    client.get_native_asset.assert_awaited_once_with(PROJECT, started.media_ids[0])


def test_promotion_dispatch_target_must_match_checkpoint():
    started = module.new_promotion_started(PROJECT, MEDIA, WORKFLOW, "720p")
    with pytest.raises(module.ConfigurationError):
        module.promotion_args(
            started, model_key="native", aspect="16:9", resolution="4k", token="token"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["foreign", "partial", "malformed", "mixed-arms", "bad-url"])
async def test_source_refuses_contradictions_before_measurement(monkeypatch, fault):
    owned(monkeypatch)
    row = [
        MEDIA,
        PROJECT,
        WORKFLOW,
        None,
        None,
        None,
        None,
        [
            None,
            [None, None],
            None,
            None,
            [None, None, "https://flow-content.google/video/test.mp4"],
        ],
    ]
    if fault == "foreign":
        row[1] = MEDIA
    if fault == "partial":
        row[7][1] = [None, 360]
    if fault == "malformed":
        row[7][1] = []
    if fault == "mixed-arms":
        row[6] = []
    if fault == "bad-url":
        row[7][4][2] = "https://example.org/private"
    monkeypatch.setattr(module, "read_project_payload", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "native_rpc", AsyncMock(return_value=row))
    download = AsyncMock()
    monkeypatch.setattr("gflow_cli.api.transports.native_asset_download.download_asset", download)
    with pytest.raises(ValueError):
        await module.read_promotion_source(Mock(), project_id=PROJECT, media_id=MEDIA)
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_sdk_missing_output_dimensions_use_bounded_measurement(monkeypatch):
    started = module.new_promotion_started(PROJECT, MEDIA, WORKFLOW, "720p")
    monkeypatch.setattr(module, "wait_native_extension", AsyncMock(return_value=("poll-record",)))
    asset = NativeAsset(
        started.media_ids[0],
        PROJECT,
        WORKFLOW,
        "video",
        "https://flow-content.google/video/test.mp4",
        None,
        None,
    )
    client = SimpleNamespace(get_native_asset=AsyncMock(return_value=asset))
    download = AsyncMock(return_value=SimpleNamespace(width=1280, height=720))
    monkeypatch.setattr("gflow_cli.api.transports.native_asset_download.download_asset", download)
    assert await module.wait_native_promotion(client, started) == ("poll-record",)
    assert not download.call_args.args[1].exists()


@pytest.mark.asyncio
async def test_output_cannot_change_inherited_portrait_to_landscape(monkeypatch):
    started = replace(
        module.new_promotion_started(PROJECT, MEDIA, WORKFLOW, "720p"), source_aspect="9:16"
    )
    monkeypatch.setattr(module, "wait_native_extension", AsyncMock(return_value=("poll-record",)))
    asset = NativeAsset(
        started.media_ids[0],
        PROJECT,
        WORKFLOW,
        "video",
        "https://flow-content.google/video/test.mp4",
        1280,
        720,
    )
    client = SimpleNamespace(get_native_asset=AsyncMock(return_value=asset))
    with pytest.raises(module.NativeVideoUpscaleUnknownError):
        await module.wait_native_promotion(client, started)
