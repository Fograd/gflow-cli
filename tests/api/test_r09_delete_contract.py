"""Individual deletion boundaries and recovery; no real mutation requests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from gflow_cli.api.transports import native_media_delete as delete
from gflow_cli.api.transports.migrated_rpc import NativeMetadataRpcError
from gflow_cli.errors import NativeMediaMutationUnknownError

P = "11111111-1111-4111-8111-111111111111"
M = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
N = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
W = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def page():
    return MagicMock(url="https://flow.google.com/project/" + P, wait_for_function=AsyncMock())


def owned(identifier, kind="image"):
    row = [identifier, P, W, None, None, None, None, None, None, None, None]
    row[{"image": 6, "video": 7, "audio": 10}[kind]] = [[1]]
    return row


def test_distinct_limit_applies_after_canonical_ordered_normalization():
    ids = [str(UUID(int=i + 1)) for i in range(100)]
    assert delete.validate_delete(P.upper(), [M.upper(), N, M, N.upper()], True) == (
        P,
        (M, N),
    )
    assert delete.validate_delete(P, ids + ids, True)[1] == tuple(ids)
    with pytest.raises(ValueError, match="1 to 100"):
        delete.validate_delete(P, ids + [M], True)


@pytest.mark.parametrize("values", [[], [M, None], [M, 1], [M, "foreign"], M])
async def test_invalid_batch_refuses_before_page(values):
    with pytest.raises(ValueError):
        await delete.delete_individual_media(None, P, values, True)


async def test_hundred_owned_ids_all_preflight_before_one_media_only_write(monkeypatch):
    ids = [str(UUID(int=i + 1)) for i in range(100)]
    rpc = AsyncMock(side_effect=[*[owned(i, "video") for i in ids], []])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    result = await delete.delete_individual_media(page(), P, ids + ids, True)
    assert result["deleted"] == ids
    assert [call.args[1] for call in rpc.await_args_list] == ["as29s"] * 100 + ["cz8Z4b"]
    assert rpc.await_args_list[-1].args[2] == [None, None, P, None, None, None, ids]


@pytest.mark.parametrize("failure", [OSError("uncertain"), asyncio.CancelledError()])
async def test_mixed_uncertain_write_retains_confirmed_ids_and_only_pending_present(
    monkeypatch, failure
):
    receipts = MagicMock()
    receipts.kind.return_value = "image"
    rpc = AsyncMock(side_effect=[NativeMetadataRpcError("as29s", 5), owned(N), failure])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises((NativeMediaMutationUnknownError, asyncio.CancelledError)) as caught:
        await delete.delete_individual_media(page(), P, [M, N], True, receipts=receipts)
    error = caught.value
    if isinstance(error, asyncio.CancelledError):
        error = vars(error)["gflow_native_media_unknown"]
    assert error.known_media_ids == (M,)
    assert error.pending_media_ids == (N,)
    assert rpc.await_count == 3
    receipts.record.assert_not_called()


async def test_interruption_during_receipt_persistence_preserves_google_ack(monkeypatch):
    receipts = MagicMock()
    receipts.record.side_effect = [None, asyncio.CancelledError()]
    rpc = AsyncMock(side_effect=[owned(M), owned(N, "video"), []])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises(asyncio.CancelledError) as caught:
        await delete.delete_individual_media(page(), P, [M, N], True, receipts=receipts)
    recovery = vars(caught.value)["gflow_native_media_unknown"]
    assert recovery.known_media_ids == (M, N)
    assert recovery.pending_media_ids == ()
    assert rpc.await_count == 3


async def test_stale_present_listing_or_receipt_does_not_skip_exact_ownership(monkeypatch):
    receipts = MagicMock()
    receipts.kind.return_value = "image"
    row = owned(N)
    row[1] = W
    rpc = AsyncMock(side_effect=[owned(M), row])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises(ValueError, match="ownership"):
        await delete.delete_individual_media(page(), P, [M, N], True, receipts=receipts)
    assert [call.args[1] for call in rpc.await_args_list] == ["as29s", "as29s"]
    receipts.record.assert_not_called()
