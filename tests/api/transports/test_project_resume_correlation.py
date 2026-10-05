"""Empty resumed catalogs still require the selected authenticated request context."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.transports import migrated_resources as module

P = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
BASE = "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=Zzl0ze"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_url",
    [
        BASE,
        BASE + "&source-path=/project/" + P2,
        BASE + "&source-path=/project/" + P + "&source-path=/project/" + P2,
        BASE.replace("https:", "http:") + "&source-path=/project/" + P,
        BASE.replace("flow.google.com", "example.org") + "&source-path=/project/" + P,
        BASE.replace("flow.google.com", "flow.google.com:444") + "&source-path=/project/" + P,
        BASE.replace("flow.google.com", "user@flow.google.com") + "&source-path=/project/" + P,
        BASE + "&source-path=/project/" + P + "&source-path=",
    ],
)
async def test_unrelated_empty_reply_is_ignored_before_accepting_correlated_reply(
    monkeypatch, bad_url
):
    wanted = [None, [], [], [], None, None]
    unrelated = SimpleNamespace(
        url=bad_url, headers={}, text=AsyncMock(return_value=json.dumps(wanted))
    )
    selected = SimpleNamespace(
        url=BASE + "&source-path=/project/" + P,
        headers={},
        text=AsyncMock(return_value=json.dumps(wanted)),
    )
    listeners = {}
    page = SimpleNamespace(
        on=Mock(side_effect=lambda event, cb: listeners.update({event: cb})), remove_listener=Mock()
    )

    async def goto(url):
        await listeners["response"](unrelated)
        await listeners["response"](selected)

    page.goto = AsyncMock(side_effect=goto)
    monkeypatch.setattr(module, "parse_frames", lambda raw: [("Zzl0ze", json.loads(raw))])
    assert await module.read_project_payload(page, P, require_request_project=True) == wanted
    unrelated.text.assert_not_awaited()
    selected.text.assert_awaited_once()
    page.remove_listener.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_empty", [False, True])
async def test_measured_null_catalog_requires_opt_in_and_correlated_reply(monkeypatch, allow_empty):
    wanted = [None, None, None, [], None, None, None, []]
    selected = SimpleNamespace(
        status=200,
        url=BASE + "&source-path=/project/" + P,
        headers={},
        text=AsyncMock(return_value=json.dumps(wanted)),
    )
    listeners = {}
    page = SimpleNamespace(
        on=Mock(side_effect=lambda event, cb: listeners.update({event: cb})), remove_listener=Mock()
    )

    async def goto(url):
        await listeners["response"](selected)

    page.goto = AsyncMock(side_effect=goto)
    monkeypatch.setattr(module, "parse_frames", lambda raw: [("Zzl0ze", json.loads(raw))])
    if allow_empty:
        result = await module.read_project_payload(
            page, P, require_request_project=True, allow_empty_catalog=True
        )
        assert result == [None, [], [], [], None, None, None, []]
    else:
        with pytest.raises(ValueError, match="unsupported shape"):
            await module.read_project_payload(page, P, require_request_project=True)


@pytest.mark.asyncio
async def test_empty_catalog_opt_in_refuses_without_exact_request_scope():
    with pytest.raises(ValueError, match="exact project"):
        await module.read_project_payload(None, P, allow_empty_catalog=True)
