"""Populated projects exceed legacy tiny RPCs, with a bounded shared read budget."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.transports import migrated_resources as subject
from gflow_cli.api.transports import migrated_upload_drain as drains

P = "22222222-2222-4222-8222-222222222222"
LIMIT = 16 * 1024 * 1024


def page_with_response(monkeypatch, body, headers):
    selected = SimpleNamespace(
        status=200,
        url="https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=Zzl0ze&source-path=/project/"
        + P,
        headers=headers,
        text=AsyncMock(return_value=body),
    )
    listeners = {}
    page = SimpleNamespace(
        on=Mock(side_effect=lambda event, handler: listeners.update({event: handler})),
        remove_listener=Mock(),
    )

    async def goto(url):
        await listeners["response"](selected)

    page.goto = AsyncMock(side_effect=goto)
    monkeypatch.setattr(subject, "parse_frames", lambda text: [("Zzl0ze", json.loads(text))])
    monkeypatch.setattr(drains.UploadResponseDrain, "install", AsyncMock())
    monkeypatch.setattr(drains.UploadResponseDrain, "close", AsyncMock())
    monkeypatch.setattr(
        drains.UploadResponseDrain,
        "result",
        AsyncMock(return_value=drains.DrainObservation(True, True, len(body.encode()), 1, LIMIT)),
    )
    return page, selected


@pytest.mark.asyncio
@pytest.mark.parametrize("advertise_length", [False, True])
async def test_valid_project_metadata_larger_than_two_mib_can_be_read(
    monkeypatch, advertise_length
):
    payload = [None, [], [], [], None, "x" * (3 * 1024 * 1024)]
    body = json.dumps(payload)
    headers = {"content-length": str(len(body))} if advertise_length else {}
    page, response = page_with_response(monkeypatch, body, headers)
    assert await subject.read_project_payload(page, P, require_request_project=True) == payload
    response.text.assert_awaited_once()
    page.remove_listener.assert_called_once()


@pytest.mark.asyncio
async def test_project_limit_advertised_before_body_is_still_enforced(monkeypatch):
    page, response = page_with_response(monkeypatch, "PRIVATE", {"content-length": str(LIMIT + 1)})
    with pytest.raises(ValueError, match="16 MiB") as error:
        await subject.read_project_payload(page, P)
    assert "PRIVATE" not in str(error.value)
    response.text.assert_not_awaited()
    page.remove_listener.assert_called_once()


@pytest.mark.asyncio
async def test_unadvertised_utf8_body_over_the_budget_is_still_rejected(monkeypatch):
    page, response = page_with_response(monkeypatch, "é" * (LIMIT // 2 + 1), {})
    with pytest.raises(ValueError, match="16 MiB"):
        await subject.read_project_payload(page, P)
    response.text.assert_awaited_once()
    page.remove_listener.assert_called_once()


def test_only_project_rpc_receives_the_larger_drain_budget():
    assert drains._RPC_BUDGETS["Zzl0ze"] == (LIMIT, 30_000)
    assert drains._RPC_BUDGETS["maseQ"] == (1024 * 1024, 60_000)
    assert drains._RPC_BUDGETS["ogiZ0b"] == (2 * 1024 * 1024, 180_000)
