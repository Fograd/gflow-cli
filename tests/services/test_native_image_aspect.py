from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.errors import ConfigurationError
from gflow_cli.services import image_aspect

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", [None, "video", "archived", "dimensions", "duplicate", "oversized", "membership"]
)
async def test_native_auto_fresh_owned_dimensions(monkeypatch, invalid):
    client = MagicMock()
    page = MagicMock()
    client.settings.flow_host = "flow.google.com"
    client._checkout_page = AsyncMock(return_value=page)
    payload = object()
    read = AsyncMock(return_value=payload)
    row = dict(media_id=M, workflow_id=W, kind="image", width=1536, height=1024)
    if invalid == "video":
        row["kind"] = "video"
    if invalid == "oversized":
        row.update(width=100000, height=100000)
    if invalid == "dimensions":
        row.pop("width")
    monkeypatch.setattr(image_aspect, "read_project_payload", read)
    monkeypatch.setattr(
        image_aspect,
        "parse_media_snapshot",
        lambda p, project: {"media": [row, row] if invalid == "duplicate" else [row]},
    )
    monkeypatch.setattr(
        image_aspect,
        "project_media",
        lambda p, project: [
            dict(
                workflow_id=W,
                project_id=P,
                archived=invalid == "archived",
                media_id=W if invalid == "membership" else M,
                batch_media_ids=[],
            )
        ],
    )
    if invalid:
        with pytest.raises(ConfigurationError):
            await image_aspect.resolve_native_image_aspect(client, P, M)
    else:
        aspect, decision = await image_aspect.resolve_native_image_aspect(client, P, M)
        assert aspect == image_aspect.Aspect.from_cli("4:3")
        assert image_aspect.aspect_decision_metadata(decision)["requestedAspectRatio"] == "auto"
    read.assert_awaited_once_with(page, P)
    client._checkin_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_canonical_uuid_and_batch_sibling_use_real_parsers(monkeypatch):
    project = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    media = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    primary = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    payload = [
        None,
        [[W, None, None, ["caption", None, False, None, primary], project]],
        [
            [media, project, W, None, None, None, [None, None, [300, 400]], None],
            [primary, project, W, None, None, None, [None, None, [300, 400]], None],
        ],
    ]
    client = MagicMock()
    page = MagicMock()
    client.settings.flow_host = "flow.google.com"
    client._checkout_page = AsyncMock(return_value=page)
    read = AsyncMock(return_value=payload)
    monkeypatch.setattr(image_aspect, "read_project_payload", read)
    _, decision = await image_aspect.resolve_native_image_aspect(
        client, project.upper(), media.upper()
    )
    assert decision.resolved_aspect == "3:4"
    read.assert_awaited_once_with(page, project)
    client._checkin_page.assert_called_once_with(page)
