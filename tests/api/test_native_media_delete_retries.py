from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.transports import migrated_rpc as rpcmod
from gflow_cli.api.transports import native_media_delete as delete

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"


async def test_exact_not_found_is_typed():
    page = MagicMock(
        evaluate=AsyncMock(
            return_value={
                "status": 200,
                "text": '[["wrb.fr","as29s",null,null,null,[5],"generic"]]',
            }
        )
    )
    with pytest.raises(rpcmod.NativeMetadataRpcError) as caught:
        await rpcmod.native_rpc(page, "as29s", [M], "/project/" + P, require_single=True)
    assert caught.value.rpcid == "as29s" and caught.value.code == 5


async def test_confirmed_gone_receipt_never_replays_delete(monkeypatch):
    store = MagicMock()
    store.kind.return_value = "image"
    rpc = AsyncMock(side_effect=rpcmod.NativeMetadataRpcError("as29s", 5))
    monkeypatch.setattr(delete, "native_rpc", rpc)
    result = await delete.delete_individual_media(
        MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M], True, receipts=store
    )
    assert result["already_deleted"] == [M] and result["deleted"] == [M]
    assert result["newly_deleted"] == []
    assert [c.args[1] for c in rpc.await_args_list] == ["as29s"]


async def test_mixed_batch_only_deletes_present_ids(monkeypatch):
    store = MagicMock()
    store.kind.return_value = "image"
    rpc = AsyncMock(
        side_effect=[
            rpcmod.NativeMetadataRpcError("as29s", 5),
            [N, P, W, None, None, None, [[1]]],
            [],
        ]
    )
    monkeypatch.setattr(delete, "native_rpc", rpc)
    result = await delete.delete_individual_media(
        MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M, N], True, receipts=store
    )
    assert result["deleted"] == [M, N] and result["newly_deleted"] == [N]
    assert rpc.await_args_list[-1].args[2][-1] == [N]
    store.record.assert_called_once_with(N, "image")


async def test_unknown_missing_id_blocks_whole_batch(monkeypatch):
    store = MagicMock()
    store.kind.return_value = None
    rpc = AsyncMock(
        side_effect=[[M, P, W, None, None, None, [[1]]], rpcmod.NativeMetadataRpcError("as29s", 5)]
    )
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await delete.delete_individual_media(
            MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()),
            P,
            [M, N],
            True,
            receipts=store,
        )
    assert [c.args[1] for c in rpc.await_args_list] == ["as29s", "as29s"]
    store.record.assert_not_called()


@pytest.mark.parametrize("code", [7, 16, None, True])
async def test_other_rpc_failure_never_counts_as_already_deleted(monkeypatch, code):
    store = MagicMock()
    store.kind.return_value = "image"
    rpc = AsyncMock(side_effect=rpcmod.NativeMetadataRpcError("as29s", code))
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await delete.delete_individual_media(
            MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M], True, receipts=store
        )
    store.record.assert_not_called()
    assert len(rpc.await_args_list) == 1


async def test_receipt_failure_preserves_acknowledged_delete(monkeypatch):
    store = MagicMock()
    store.record.side_effect = OSError("disk")
    rpc = AsyncMock(side_effect=[[M, P, W, None, None, None, [[1]]], []])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    result = await delete.delete_individual_media(
        MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M], True, receipts=store
    )
    assert result["deleted"] == [M] and result["receipt_persisted"] is False
    assert len(rpc.await_args_list) == 2


@pytest.mark.parametrize(
    "text",
    [
        '[["wrb.fr","as29s",null,null,null,[5],"generic"],["wrb.fr","as29s",null,null,null,[5],"generic"]]',
        '[["wrb.fr","as29s","[]",null,null,null,"generic"],["wrb.fr","as29s",null,null,null,[5],"generic"]]',
        '[["wrb.fr","as29s",null,null,null,null,"generic"]]',
    ],
)
async def test_ambiguous_or_untyped_missing_is_not_typed_not_found(text):
    page = MagicMock(evaluate=AsyncMock(return_value={"status": 200, "text": text}))
    with pytest.raises(ValueError) as caught:
        await rpcmod.native_rpc(page, "as29s", [M], "/project/" + P, require_single=True)
    assert not isinstance(caught.value, rpcmod.NativeMetadataRpcError)


@pytest.mark.parametrize("payload", ["null", "not-json"])
async def test_success_plus_malformed_same_rpc_is_never_acknowledged(payload):
    import json

    text = json.dumps(
        [
            ["wrb.fr", "cz8Z4b", "[]", None, None, None, "generic"],
            [
                "wrb.fr",
                "cz8Z4b",
                None if payload == "null" else payload,
                None,
                None,
                None,
                "generic",
            ],
        ]
    )
    page = MagicMock(evaluate=AsyncMock(return_value={"status": 200, "text": text}))
    with pytest.raises(ValueError):
        await rpcmod.native_rpc(page, "cz8Z4b", [], "/project/" + P, require_single=True)
