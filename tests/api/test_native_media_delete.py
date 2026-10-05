from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.transports import native_media_delete as delete

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"
N = "44444444-4444-4444-8444-444444444444"


@pytest.mark.asyncio
async def test_media_only_delete_does_not_send_workflow_siblings(monkeypatch):
    row = [M, P, W, None, None, None, [[1]]]
    rpc = AsyncMock(side_effect=[row, []])
    monkeypatch.setattr(delete, "native_rpc", rpc)
    result = await delete.delete_individual_media(
        MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M], True
    )
    assert result["deleted"] == [M]
    assert rpc.await_args_list[-1].args[1:3] == ("cz8Z4b", [None, None, P, None, None, None, [M]])
    assert W not in str(rpc.await_args_list[-1].args[2])


@pytest.mark.asyncio
async def test_all_ownership_preflight_before_delete(monkeypatch):
    rpc = AsyncMock(
        side_effect=[[M, P, W, None, None, None, [[1]]], [N, W, W, None, None, None, [[1]]]]
    )
    monkeypatch.setattr(delete, "native_rpc", rpc)
    with pytest.raises(ValueError):
        await delete.delete_individual_media(
            MagicMock(goto=AsyncMock(), wait_for_function=AsyncMock()), P, [M, N], True
        )
    assert [call.args[1] for call in rpc.await_args_list] == ["as29s", "as29s"]


@pytest.mark.asyncio
async def test_confirmation_fails_and_uuid_duplicates_normalize_before_page(monkeypatch):
    rpc = AsyncMock()
    monkeypatch.setattr(delete, "native_rpc", rpc)
    for confirmation in [False, 1, "true"]:
        with pytest.raises(ValueError):
            await delete.delete_individual_media(None, P, [M], confirmation)
    assert delete.validate_delete(P, [M, M.upper()], True) == (P, (M,))
    rpc.assert_not_awaited()
