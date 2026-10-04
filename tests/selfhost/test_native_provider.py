"""Before-Google configured provider fallback, no live provider calls."""

from types import SimpleNamespace

import pytest

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_submission,
    take_native_captcha_token_async,
)
from gflow_cli.selfhost import native_provider as provider
from gflow_cli.selfhost.captcha import SolverError

P = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
async def test_fresh_sitekey_fallback_and_accepted_download_failure(tmp_path, monkeypatch):
    calls = []
    events = []

    class Keys:
        def __init__(self, path):
            pass

        def get(self, name):
            return "configured"

    class Stats:
        def __init__(self, path):
            pass

        def record(self, name, phase):
            events.append((name, phase))

    async def discover(page):
        calls.append("sitekey")
        return "fresh-public-key"

    class Solver:
        async def solve(self, name, key, url, sitekey, action):
            calls.append((name, url, sitekey, action))
            if name == "CapSolver":
                raise SolverError("masked")
            return SimpleNamespace(token="x" * 40)

    monkeypatch.setattr(provider, "ProviderKeys", Keys)
    monkeypatch.setattr(provider, "CaptchaStats", Stats)
    monkeypatch.setattr(provider, "discover_site_key", discover)
    monkeypatch.setattr(provider, "Solver", Solver)
    page = SimpleNamespace(url=f"https://flow.google.com/project/{P}")
    with pytest.raises(OSError):
        with provider.native_provider_context(
            {"captchaOrder": "CapSolver,2Captcha", "captchaRetry": 1},
            P,
            "VIDEO_GENERATION",
            root=tmp_path,
        ):
            assert await take_native_captcha_token_async(page, "VIDEO_GENERATION") == "x" * 40
            native_captcha_submission()
            native_captcha_outcome("accepted")
            raise OSError("later download failure")
    assert calls[0] == "sitekey"
    assert [call[0] for call in calls[1:]] == ["CapSolver", "2Captcha"]
    assert events == [
        ("CapSolver", "solveStarted"),
        ("CapSolver", "solveFailed"),
        ("2Captcha", "solveStarted"),
        ("2Captcha", "solved"),
        ("2Captcha", "submitted"),
        ("2Captcha", "accepted"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"captchaRetry": 2},
        {"captchaRetry": True},
        {"captchaOrder": "Unknown"},
        {"captchaOrder": "CapSolver,CapSolver"},
    ],
)
def test_invalid_controls_refuse_before_provider(payload, tmp_path):
    with pytest.raises(ValueError):
        with provider.native_provider_context(payload, P, "VIDEO_GENERATION", root=tmp_path):
            pass


@pytest.mark.asyncio
async def test_navigation_during_fresh_discovery_never_starts_solver(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    class Keys:
        def __init__(self, _path):
            pass

        def get(self, _name):
            return "configured"

    page = SimpleNamespace(url=f"https://flow.google.com/project/{P}")

    async def discover(current):
        current.url = "https://flow.google.com/project/22222222-2222-4222-8222-222222222222"
        return "fresh-key"

    solve = AsyncMock()
    monkeypatch.setattr(provider, "ProviderKeys", Keys)
    monkeypatch.setattr(provider, "discover_site_key", discover)
    monkeypatch.setattr(provider, "Solver", lambda: SimpleNamespace(solve=solve))
    with provider.native_provider_context(
        {"captchaRetry": 1}, P, "VIDEO_GENERATION", root=tmp_path
    ):
        with pytest.raises(SolverError):
            await take_native_captcha_token_async(page, "VIDEO_GENERATION")
    solve.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_provider_token_is_failed_solve_before_fallback(tmp_path, monkeypatch):
    calls = []
    events = []

    class Keys:
        def __init__(self, _path):
            pass

        def get(self, _name):
            return "configured"

    class Stats:
        def __init__(self, _path):
            pass

        def record(self, name, phase):
            events.append((name, phase))

    async def discover(_page):
        return "fresh-key"

    class Solver:
        async def solve(self, name, *args):
            calls.append(name)
            return SimpleNamespace(token=("a" * 39 + " ") if name == "CapSolver" else "b" * 40)

    monkeypatch.setattr(provider, "ProviderKeys", Keys)
    monkeypatch.setattr(provider, "CaptchaStats", Stats)
    monkeypatch.setattr(provider, "discover_site_key", discover)
    monkeypatch.setattr(provider, "Solver", Solver)
    page = SimpleNamespace(url=f"https://flow.google.com/project/{P}")
    with provider.native_provider_context(
        {"captchaOrder": "CapSolver,2Captcha"}, P, "VIDEO_GENERATION", root=tmp_path
    ):
        assert await take_native_captcha_token_async(page, "VIDEO_GENERATION") == "b" * 40
    assert calls == ["CapSolver", "2Captcha"]
    assert events == [
        ("CapSolver", "solveStarted"),
        ("CapSolver", "solveFailed"),
        ("2Captcha", "solveStarted"),
        ("2Captcha", "solved"),
    ]
