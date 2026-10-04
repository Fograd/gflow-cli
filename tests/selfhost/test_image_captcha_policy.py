from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.errors import WafRejectionError
from gflow_cli.selfhost.image_captcha_policy import run_with_image_captcha_policy

PROJECT = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [1, 2, 10])
async def test_only_positive_dispatched_refusal_retries(monkeypatch, tmp_path, budget):
    seen = []

    async def attempt(override):
        seen.append(override)
        override.used = True
        override.mark_submitted()
        override.outcome("rejected")
        raise WafRejectionError(detail="redacted")

    with pytest.raises(WafRejectionError):
        await run_with_image_captcha_policy(
            {"count": 1, "captchaRetry": budget}, PROJECT, tmp_path, attempt
        )
    assert len(seen) == budget
    assert len({id(value) for value in seen}) == budget
    assert all(value.closed for value in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", [None, "accepted", "unknown"])
async def test_waf_without_positive_refusal_does_not_retry(tmp_path, phase):
    attempt_count = 0

    async def attempt(override):
        nonlocal attempt_count
        attempt_count += 1
        override.used = True
        override.mark_submitted()
        if phase:
            override.outcome(phase)
        raise WafRejectionError(detail="redacted")

    with pytest.raises(WafRejectionError):
        await run_with_image_captcha_policy(
            {"count": 1, "captchaRetry": 10}, PROJECT, tmp_path, attempt
        )
    assert attempt_count == 1


@pytest.mark.asyncio
async def test_invalid_token_falls_back_before_submission(monkeypatch, tmp_path):
    import time

    import gflow_cli.selfhost.image_captcha_policy as policy
    from gflow_cli.selfhost.captcha import CaptchaStats

    monkeypatch.setattr(policy.ProviderKeys, "get", lambda *_: "private-key")
    monkeypatch.setattr(policy, "discover_site_key", AsyncMock(return_value="public-key"))
    solve = AsyncMock(
        side_effect=[
            SimpleNamespace(token="invalid token"),
            SimpleNamespace(token="replacement" * 5),
        ]
    )
    monkeypatch.setattr(policy.Solver, "solve", solve)

    async def attempt(override):
        override.metadata = {"sitekey": "public-key", "action": "IMAGE_GENERATION"}
        override.metadata_url = "https://flow.google.com/project/" + PROJECT
        override.metadata_at = time.monotonic()
        token = await override.token(SimpleNamespace(url=override.metadata_url))
        assert token == "replacement" * 5
        override.used = True
        override.mark_submitted()
        override.outcome("accepted")
        return "done"

    result, chosen = await run_with_image_captcha_policy(
        {"count": 1, "captchaOrder": "CapSolver,2Captcha"}, PROJECT, tmp_path, attempt
    )
    assert (result, chosen) == ("done", "2Captcha")
    counts = CaptchaStats(tmp_path).public()["providers"]
    assert counts["CapSolver"] == {"solveStarted": 1, "solveFailed": 1}
    assert counts["2Captcha"] == {"solveStarted": 1, "solved": 1, "submitted": 1, "accepted": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [True, 0, 11, "2", 1.5])
async def test_invalid_retry_refuses_before_attempt(tmp_path, budget):
    attempt = AsyncMock()
    with pytest.raises(ValueError):
        await run_with_image_captcha_policy(
            {"count": 1, "captchaRetry": budget}, PROJECT, tmp_path, attempt
        )
    attempt.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["stale", "wrong-key", "navigation"])
async def test_current_metadata_and_page_required_before_solve(monkeypatch, tmp_path, fault):
    import time

    import gflow_cli.selfhost.image_captcha_policy as policy
    from gflow_cli.selfhost.captcha import SolverError

    solve = AsyncMock()
    monkeypatch.setattr(policy.Solver, "solve", solve)
    page = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)

    async def discover(page):
        if fault == "navigation":
            page.url = "https://flow.google.com/project/foreign"
        return "wrong" if fault == "wrong-key" else "public-key"

    monkeypatch.setattr(policy, "discover_site_key", discover)

    async def attempt(override):
        override.metadata = {"sitekey": "public-key", "action": "IMAGE_GENERATION"}
        override.metadata_url = page.url
        override.metadata_at = time.monotonic() - (121 if fault == "stale" else 0)
        await override.token(page)

    with pytest.raises(SolverError):
        await run_with_image_captcha_policy(
            {"count": 1, "captchaRetry": 10}, PROJECT, tmp_path, attempt
        )
    solve.assert_not_called()


@pytest.mark.asyncio
async def test_supplied_token_wins_and_forces_one_sequence(monkeypatch, tmp_path):
    import gflow_cli.selfhost.image_captcha_policy as policy

    solve = AsyncMock()
    monkeypatch.setattr(policy.Solver, "solve", solve)
    directory = tmp_path / "captcha-input"
    directory.mkdir()
    path = directory / (("a" * 64) + ".token")
    path.write_text("provided" * 5)
    path.chmod(0o600)
    seen = []

    async def attempt(override):
        seen.append(override)
        page = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)
        assert await override.token(page) == "provided" * 5
        override.used = True
        override.mark_submitted()
        override.outcome("rejected")
        raise WafRejectionError(detail="redacted")

    with pytest.raises(WafRejectionError):
        await run_with_image_captcha_policy(
            {
                "count": 1,
                "captchaOrder": "CapSolver",
                "captchaRetry": 10,
                "captchaSecret": str(path),
            },
            PROJECT,
            tmp_path,
            attempt,
        )
    assert len(seen) == 1
    assert not path.exists()
    solve.assert_not_called()


@pytest.mark.asyncio
async def test_default_path_keeps_browser_token(tmp_path):
    async def attempt(override):
        assert override.token is None
        assert override.seed == 7
        return "browser-result"

    assert await run_with_image_captcha_policy(
        {"count": 1, "seed": 7}, PROJECT, tmp_path, attempt
    ) == ("browser-result", None)
