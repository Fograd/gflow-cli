"""Fresh current-user codec/transport; synthetic source shapes, no network."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.auth.native_identity import (
    native_identity_args,
    parse_native_identity,
    read_native_identity,
)

EMAIL = "synthetic@example.test"


def person_reply(*, status=1, selector="me", emails=None):
    person = [None] * 10
    person[9] = [[None, EMAIL]] if emails is None else emails
    return [[[selector, status, person]]]


def test_exact_primary_me_request_mask():
    assert native_identity_args() == [
        ["me"],
        [[["person.photo", "person.name", "person.email", "person.metadata"]], None, [1, 7, 10]],
    ]
    first = native_identity_args()
    first[0].append("another")
    assert native_identity_args()[0] == ["me"]


@pytest.mark.parametrize("status", [1])
def test_single_me_principal_with_default_lookup_status(status):
    assert parse_native_identity(person_reply(status=status)) == EMAIL


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [None],
        [[[]]],
        person_reply(status=True),
        person_reply(status=0),
        person_reply(status=None),
        person_reply(status="0"),
        person_reply(selector="another"),
        person_reply(emails=[]),
        person_reply(emails=[[None, EMAIL], [None, EMAIL]]),
        person_reply(emails=[[None, "not-an-email"]]),
        person_reply(emails=[[None, "private\nvalue@example.test"]]),
        person_reply(emails=[[None, "x" * 256 + "@example.test"]]),
        [[person_reply()[0][0], person_reply()[0][0]]],
    ],
)
def test_unknown_or_ambiguous_principal_refuses(payload):
    with pytest.raises(ValueError, match="Native current principal is unavailable"):
        parse_native_identity(payload)


@pytest.mark.asyncio
async def test_reader_requires_fresh_singleton_same_origin_rpc(monkeypatch):
    page = SimpleNamespace(url="https://flow.google.com/u/0/")
    rpc = AsyncMock(return_value=person_reply())
    monkeypatch.setattr("gflow_cli.auth.native_identity.native_rpc", rpc)
    assert await read_native_identity(page) == EMAIL
    rpc.assert_awaited_once_with(
        page, "o30O0e", native_identity_args(), "/u/0/", require_single=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://flow.google.com/u/0/",
        "https://flow.google.com.evil.test/u/0/",
        "https://other.test/",
        "https://flow.google.com:444/u/0/",
    ],
)
async def test_reader_refuses_foreign_origin_before_rpc(monkeypatch, url):
    rpc = AsyncMock(return_value=person_reply())
    monkeypatch.setattr("gflow_cli.auth.native_identity.native_rpc", rpc)
    with pytest.raises(ValueError):
        await read_native_identity(SimpleNamespace(url=url))
    rpc.assert_not_awaited()


@pytest.mark.asyncio
async def test_reader_origin_transition_cannot_attest_identity(monkeypatch):
    page = SimpleNamespace(url="https://flow.google.com/u/0/")

    async def changed(*args, **kwargs):
        page.url = "https://other.test/"
        return person_reply()

    monkeypatch.setattr("gflow_cli.auth.native_identity.native_rpc", changed)
    with pytest.raises(ValueError):
        await read_native_identity(page)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows",
    [
        [],
        [["wrb.fr", "o30O0e", None]],
        [["wrb.fr", "o30O0e", json.dumps(person_reply())], ["wrb.fr", "o30O0e", None]],
    ],
)
async def test_actual_native_rpc_singleton_missing_or_masked_response_refuses(rows):
    page = SimpleNamespace(
        url="https://flow.google.com/u/0/",
        evaluate=AsyncMock(return_value={"status": 200, "text": json.dumps(rows)}),
    )
    with pytest.raises(ValueError):
        await read_native_identity(page)


@pytest.mark.asyncio
async def test_actual_native_rpc_codec_positive_and_exact_guard_script():
    page = SimpleNamespace(
        url="https://flow.google.com/u/0/",
        evaluate=AsyncMock(
            return_value={
                "status": 200,
                "text": json.dumps([["wrb.fr", "o30O0e", json.dumps(person_reply())]]),
            }
        ),
    )
    assert await read_native_identity(page) == EMAIL
    script, params = page.evaluate.call_args.args
    assert params["rpc"] == "o30O0e" and params["args"] == native_identity_args()
    assert "location.origin" in script and "r.url" in script


@pytest.mark.asyncio
async def test_reader_binds_project_source_path(monkeypatch):
    project = "00000000-0000-4000-8000-000000000099"
    page = SimpleNamespace(url=f"https://flow.google.com/project/{project}?ignored=value")
    rpc = AsyncMock(return_value=person_reply())
    monkeypatch.setattr("gflow_cli.auth.native_identity.native_rpc", rpc)
    assert await read_native_identity(page) == EMAIL
    assert rpc.await_args.args[3] == f"/project/{project}"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [1, 0])
@pytest.mark.parametrize("engine", ["playwright", "patchright"])
@pytest.mark.parametrize("headless", [False, True])
async def test_fallback_uses_fresh_native_principal_not_redirected_myaccount(
    monkeypatch, tmp_path, status, engine, headless
):
    from unittest.mock import MagicMock

    from gflow_cli.auth import strategies, verification

    project = "00000000-0000-4000-8000-000000000099"
    page = SimpleNamespace(
        url=f"https://flow.google.com/project/{project}",
        goto=AsyncMock(),
        evaluate=AsyncMock(
            return_value={
                "status": 200,
                "text": json.dumps([["wrb.fr", "o30O0e", json.dumps(person_reply(status=status))]]),
            }
        ),
    )
    response = SimpleNamespace(url="https://www.google.com/", text=AsyncMock(return_value=""))
    ctx = SimpleNamespace(
        cookies=AsyncMock(
            return_value=[
                {"name": "SAPISID", "domain": ".google.com"},
                {"name": "OSID", "domain": "flow.google.com"},
            ]
        ),
        new_page=AsyncMock(return_value=page),
        close=AsyncMock(),
        request=SimpleNamespace(get=AsyncMock(return_value=response)),
    )
    pw = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=AsyncMock(return_value=ctx))
    )
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=pw)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(strategies, "async_playwright", lambda: manager)
    monkeypatch.setattr(
        verification,
        "get_settings",
        lambda: SimpleNamespace(browser_engine=engine, headless=headless),
    )
    resolver = MagicMock(return_value=lambda: manager)
    monkeypatch.setattr("gflow_cli.api._engine.resolve_async_playwright", resolver)
    tmp_path.chmod(0o700)
    for name, value in [(".gflow_browser_strategy", "chrome"), (".gflow_account", EMAIL)]:
        marker = tmp_path / name
        marker.write_text(value)
        marker.chmod(0o600)
    result = await verification._verify_migrated_host_fallback(
        tmp_path, "synthetic", project_id=project
    )
    launch = pw.chromium.launch_persistent_context.await_args.kwargs
    assert launch["headless"] is headless
    assert launch["ignore_default_args"] == ["--enable-automation"]
    assert "--disable-blink-features=AutomationControlled" in launch["args"]
    assert "--password-store=basic" in launch["args"]
    assert launch["args"].count("--restore-last-session") == 1
    if status == 1:
        assert result.user_email == EMAIL
        assert result.outcome is verification.FlowSessionOutcome.AUTHENTICATED
        ctx.request.get.assert_not_awaited()
    else:
        assert result is None
        ctx.request.get.assert_awaited_once()
    if engine == "patchright":
        resolver.assert_called_once_with(engine)
    else:
        resolver.assert_not_called()
    ctx.close.assert_awaited_once()
    assert page.goto.await_args.args == (f"https://flow.google.com/project/{project}",)


@pytest.mark.asyncio
async def test_unavailable_configured_engine_fails_closed_before_browser(monkeypatch, tmp_path):
    from gflow_cli.auth import verification

    monkeypatch.setattr(
        verification, "get_settings", lambda: SimpleNamespace(browser_engine="patchright")
    )

    def unavailable(*args):
        raise RuntimeError("Synthetic optional engine unavailable")

    monkeypatch.setattr("gflow_cli.api._engine.resolve_async_playwright", unavailable)
    assert await verification._verify_migrated_host_fallback(tmp_path, "synthetic") is None
