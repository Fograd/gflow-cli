from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports import migrated_resources as resources
from gflow_cli.errors import NativeMediaMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"
V = "55555555-5555-4555-8555-555555555555"


def row(media=M, workflow=W, **extra):
    return dict(
        media_id=media,
        workflow_id=workflow,
        project_id=P,
        archived=False,
        batch_media_ids=[media],
        **extra,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"batch_media_ids": None},
        {"batch_media_ids": "not-a-list"},
        {"batch_media_ids": [M, M]},
        {"batch_media_ids": [M, N]},
        {"batch_media_ids": ["wrong"]},
        {"archived": True},
        {"workflow_id": "bad"},
    ],
)
def test_invalid_active_owned_membership_refused(change):
    item = row()
    item.update(change)
    with pytest.raises(ValueError):
        resources.trash_payload([M], [item], P)


def test_absent_membership_refused():
    item = row()
    item.pop("batch_media_ids")
    with pytest.raises(ValueError, match="membership"):
        resources.trash_payload([M], [item], P)


@pytest.mark.asyncio
async def test_partial_ack_preserved_no_replay(monkeypatch):
    monkeypatch.setattr(resources, "read_project", AsyncMock(return_value=[row(), row(N, V)]))
    page = AsyncMock()
    monkeypatch.setattr(
        resources,
        "parse_frames",
        lambda text: [("pGCYOe", [[[W, None, None, [None, None, True], P]]])],
    )
    page.evaluate.return_value = {"status": 200, "text": "wire"}
    with pytest.raises(NativeMediaMutationUnknownError) as info:
        await resources.trash_media(page, P, [M, N])
    assert info.value.known_media_ids == (M,)
    assert info.value.pending_media_ids == (N,)
    assert info.value.retryable is False
    assert page.evaluate.await_count == 1


@pytest.mark.asyncio
async def test_response_loss_never_replays(monkeypatch):
    monkeypatch.setattr(resources, "read_project", AsyncMock(return_value=[row()]))
    page = AsyncMock()
    page.evaluate.side_effect = RuntimeError("SECRET wire body")
    with pytest.raises(NativeMediaMutationUnknownError) as info:
        await resources.trash_media(page, P, [M])
    assert info.value.pending_media_ids == (M,)
    assert "SECRET" not in str(info.value)
    assert page.evaluate.await_count == 1


def test_full_verified_sibling_batch_mutates_workflow_once():
    first, second = row(), row(N, W)
    first["batch_media_ids"] = second["batch_media_ids"] = [M, N]
    payload = resources.trash_payload([M, N], [first, second], P)
    assert len(payload[0]) == 1
    assert payload[0][0][0] == W


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, {}, {"status": 200, "text": None}])
async def test_malformed_response_retains_pending(monkeypatch, response):
    monkeypatch.setattr(resources, "read_project", AsyncMock(return_value=[row()]))
    page = AsyncMock()
    page.evaluate.return_value = response
    with pytest.raises(NativeMediaMutationUnknownError) as info:
        await resources.trash_media(page, P, [M])
    assert info.value.pending_media_ids == (M,)
    assert page.evaluate.await_count == 1
