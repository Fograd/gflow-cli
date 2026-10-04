"""Exact GetCredits response mapping, no balance or plan assumptions."""

import pytest

from gflow_cli.api.native_credits import parse_native_credits


def test_balance_known_labels_and_unknown_components():
    info = parse_native_credits([123, 1, 9, 2, 100, 23])
    assert info.credits == 123
    assert info.user_paygate_tier == "PAYGATE_TIER_ONE"
    assert info.service_tier == "SERVICE_TIER_INTERMEDIATE"
    assert info.subscription_credits is None
    assert info.sku is None


@pytest.mark.parametrize("payload", [[], [True], [-1], ["123"], {}, None])
def test_bad_balance_refuses(payload):
    with pytest.raises(ValueError):
        parse_native_credits(payload)


def test_zero_balance_and_unrecognized_tier_remain_truthful():
    info = parse_native_credits([0, 999, None, 999])
    assert info.credits == 0
    assert info.user_paygate_tier is None
    assert info.service_tier is None


@pytest.mark.asyncio
async def test_sdk_native_branch_reuses_lease_and_skips_labs(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.dto import CreditsInfo

    client = FlowApiClient(profile_dir=tmp_path / "profile")
    page = object()
    monkeypatch.setattr(client, "_uses_native_characters", lambda: True)
    monkeypatch.setattr(client, "_checkout_page", AsyncMock(return_value=page))
    checkin = Mock()
    monkeypatch.setattr(client, "_checkin_page", checkin)
    legacy = AsyncMock()
    monkeypatch.setattr(client, "_get_json", legacy)
    read = AsyncMock(return_value=CreditsInfo(credits=42))
    monkeypatch.setattr("gflow_cli.api.native_credits.read_native_credits", read)
    assert (await client.get_credits()).credits == 42
    read.assert_awaited_once_with(page)
    legacy.assert_not_called()
    checkin.assert_called_once_with(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["patchright", "playwright"])
async def test_credit_fetch_reads_page_owned_globals_in_selected_engine(monkeypatch, engine):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from gflow_cli.api import _engine
    from gflow_cli.api.native_credits import read_native_credits

    monkeypatch.setattr(_engine, "active_engine", lambda: engine)
    expected = {"isolated_context": False} if engine == "patchright" else {}
    wire = json.dumps([["wrb.fr", "nzlxg", json.dumps([42, 1, None, 2])]])

    async def evaluate(expression, args, **kwargs):
        assert "WIZ_global_data" in expression
        assert kwargs == expected
        assert args == {"rpc": "nzlxg", "args": [], "source": "/"}
        return {"status": 200, "text": wire}

    page = SimpleNamespace(evaluate=AsyncMock(side_effect=evaluate))
    assert (await read_native_credits(page)).credits == 42
    page.evaluate.assert_awaited_once()
