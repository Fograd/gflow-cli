import pytest

from gflow_cli.selfhost.captcha_diagnostic import anchor_metadata

KEY = "A" * 40


def test_anchor_records_public_key_and_presence_not_values():
    result = anchor_metadata(
        f"https://www.google.com/recaptcha/enterprise/anchor?k={KEY}&s=SECRET&co=PRIVATE"
    )
    assert result == {"sitekey": KEY, "sPresence": True, "apiDomain": "www.google.com"}
    assert "SECRET" not in str(result) and "PRIVATE" not in str(result)


@pytest.mark.parametrize(
    "url",
    [
        f"https://evil.example/recaptcha/enterprise/anchor?k={KEY}",
        f"http://www.google.com/recaptcha/enterprise/anchor?k={KEY}",
        f"https://www.google.com/recaptcha/enterprise/anchor?k={KEY}&k={KEY}",
        "https://www.google.com/recaptcha/enterprise/anchor?k=bad",
    ],
)
def test_untrusted_or_ambiguous_anchor_ignored(url):
    assert anchor_metadata(url) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("aborted", [True, False])
async def test_capture_never_calls_solver_or_exposes_cookie_values(monkeypatch, tmp_path, aborted):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import gflow_cli.selfhost.captcha_diagnostic as diagnostic
    from gflow_cli.selfhost.captcha import Solver

    events = {}
    context = SimpleNamespace(
        on=lambda key, callback: events.update({key: callback}),
        remove_listener=lambda *args: None,
        route=AsyncMock(),
        unroute=AsyncMock(),
        cookies=AsyncMock(return_value=[{"name": "recaptcha-ca-t", "value": "SECRET"}]),
        pages=[SimpleNamespace(evaluate=AsyncMock(return_value="Browser/1"))],
    )

    class Client:
        def __init__(self, **kwargs):
            self._context = context

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_image(self, **kwargs):
            events["request"](
                SimpleNamespace(
                    url=f"https://www.google.com/recaptcha/enterprise/anchor?k={KEY}&s=SECRET",
                    post_data_buffer=None,
                )
            )
            override = diagnostic.active_overrides.get()
            if aborted:
                await override.token(None)

    solver = AsyncMock()
    monkeypatch.setattr(Solver, "solve", solver)
    monkeypatch.setattr(diagnostic, "FlowApiClient", Client)
    monkeypatch.setattr(
        diagnostic,
        "get_settings",
        lambda: SimpleNamespace(
            profile_subdir=lambda _: tmp_path, flow_host="flow.google.com", transport=None
        ),
    )
    result = await diagnostic.capture("test", "project")
    assert result["generationAborted"] is aborted
    assert result["status"] == ("aborted-read" if aborted else "incomplete-read")
    assert result["cookieNames"] == ["recaptcha-ca-t"]
    assert "SECRET" not in str(result)
    solver.assert_not_called()
    context.unroute.assert_awaited_once()
    assert diagnostic.active_overrides.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,transport", [("labs.google", None), ("auto", None), ("flow.google.com", "bearer")]
)
async def test_unsupported_mode_never_creates_browser(monkeypatch, host, transport):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import gflow_cli.selfhost.captcha_diagnostic as diagnostic

    browser = Mock()
    monkeypatch.setattr(diagnostic, "FlowApiClient", browser)
    monkeypatch.setattr(
        diagnostic, "get_settings", lambda: SimpleNamespace(flow_host=host, transport=transport)
    )
    with pytest.raises(ValueError, match="explicit native"):
        await diagnostic.capture("test", "project")
    browser.assert_not_called()
