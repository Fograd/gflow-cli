"""R06 control and supplied-token observations without any external requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.native_captcha import (
    native_captcha_outcome,
    native_captcha_refused,
    native_captcha_submission,
    native_captcha_token,
    take_native_captcha_token_async,
)
from gflow_cli.errors import WafRejectionError
from gflow_cli.selfhost import video_captcha_policy
from gflow_cli.selfhost.captcha import CaptchaStats
from gflow_cli.selfhost.native_captcha import private_native_captcha
from gflow_cli.selfhost.native_captcha_policy import run_with_native_captcha_policy
from gflow_cli.services import image_captcha, video_captcha

PROJECT = "11111111-1111-4111-8111-111111111111"
TOKEN = "synthetic-private-r06-token" * 2
PAGE = SimpleNamespace(url="https://flow.google.com/project/" + PROJECT)


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", ["captcha_token", "captchaSecret"])
@pytest.mark.parametrize("control", [{"captchaOrder": "CapSolver"}, {"captchaRetry": 1}])
async def test_video_supplied_control_conflict_before_file_or_attempt(tmp_path, secret, control):
    directory = tmp_path / "captcha-input"
    directory.mkdir()
    path = directory / ("a" * 64 + ".token")
    path.write_text(TOKEN)
    path.chmod(0o600)
    attempt = AsyncMock()
    with pytest.raises(ValueError, match="combined"):
        await video_captcha_policy.run_with_video_captcha_policy(
            {"count": 1, secret: TOKEN if secret == "captcha_token" else str(path), **control},
            PROJECT,
            tmp_path,
            attempt,
        )
    attempt.assert_not_awaited()
    assert path.read_text() == TOKEN


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["accepted", "rejected", "unknown"])
async def test_supplied_video_records_submission_and_terminal(tmp_path, outcome):
    async def attempt(override):
        assert await override.token(PAGE) == TOKEN
        override.dispatched = True
        override.observe("submitted")
        if outcome != "unknown":
            override.outcome(outcome)
        return "result"

    assert await video_captcha_policy.run_with_video_captcha_policy(
        {"count": 1, "captcha_token": TOKEN}, PROJECT, tmp_path, attempt
    ) == ("result", "supplied")
    assert CaptchaStats(tmp_path).public()["providers"]["supplied"] == {
        "submitted": 1,
        outcome: 1,
    }
    assert TOKEN.encode() not in (tmp_path / "captcha-stats.sqlite3").read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["IMAGE_GENERATION", "VIDEO_GENERATION", "AUDIO_GENERATION"])
@pytest.mark.parametrize("outcome", ["accepted", "rejected", "unknown", "cancelled", "late"])
async def test_native_supplied_statistics_and_no_refusal_retry(
    tmp_path, monkeypatch, action, outcome
):
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    try:
        with native_captcha_token(TOKEN, project_id=PROJECT, action=action):
            assert await take_native_captcha_token_async(PAGE, action) == TOKEN
            native_captcha_submission()
            native_captcha_submission()
            if outcome in {"accepted", "rejected", "late"}:
                native_captcha_outcome("accepted" if outcome == "late" else outcome)
                native_captcha_outcome("unknown")
            assert not native_captcha_refused()
            if outcome == "cancelled":
                raise asyncio.CancelledError
            if outcome == "late":
                raise WafRejectionError()
    except (asyncio.CancelledError, WafRejectionError):
        pass
    terminal = "accepted" if outcome == "late" else "unknown" if outcome == "cancelled" else outcome
    assert CaptchaStats(tmp_path).public()["providers"]["supplied"] == {
        "submitted": 1,
        terminal: 1,
    }
    assert TOKEN.encode() not in (tmp_path / "captcha-stats.sqlite3").read_bytes()


@pytest.mark.asyncio
async def test_consumed_but_unsubmitted_supplied_token_has_no_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    with native_captcha_token(TOKEN, project_id=PROJECT, action="VIDEO_GENERATION"):
        native_captcha_submission()
        assert await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION") == TOKEN
    assert not (tmp_path / "captcha-stats.sqlite3").exists()


@pytest.mark.asyncio
async def test_native_private_conflict_before_consuming_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    directory = tmp_path / "captcha-input"
    directory.mkdir()
    path = directory / ("a" * 64 + ".token")
    path.write_text(TOKEN)
    path.chmod(0o600)
    with pytest.raises(ValueError, match="combined"):
        with private_native_captcha(
            {"captchaSecret": str(path), "captchaOrder": "CapSolver"}, PROJECT, "VIDEO_GENERATION"
        ):
            pytest.fail("conflicting controls reached operation")
    assert path.read_text() == TOKEN


@pytest.mark.asyncio
async def test_native_policy_conflict_before_context_or_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    attempt = AsyncMock()
    with pytest.raises(ValueError, match="combined"):
        await run_with_native_captcha_policy(
            {"captchaSecret": "private", "captchaRetry": 10}, PROJECT, "VIDEO_GENERATION", attempt
        )
    attempt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "video"])
async def test_ambient_supplied_scope_cannot_combine_with_generic_provider(tmp_path, kind):
    from gflow_cli.errors import ConfigurationError

    generate = AsyncMock()
    client = SimpleNamespace(generate_image=generate, generate_video=generate)
    wrapper = (
        image_captcha.generate_images_with_captcha
        if kind == "image"
        else video_captcha.generate_video_with_captcha
    )
    with native_captcha_token(TOKEN, project_id=PROJECT, action="VIDEO_GENERATION"):
        with pytest.raises(ConfigurationError, match="combined"):
            await wrapper(
                client,
                req=SimpleNamespace(count=1, seed=None),
                project_id=PROJECT,
                captcha_order="CapSolver",
                root=tmp_path,
            )
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_video_missing_key_is_safe_typed_configuration_error(tmp_path, monkeypatch):
    from gflow_cli.errors import ConfigurationError

    monkeypatch.setattr(
        video_captcha_policy, "ProviderKeys", lambda root: SimpleNamespace(get=lambda name: None)
    )
    solve = AsyncMock()
    monkeypatch.setattr(video_captcha_policy, "Solver", lambda: SimpleNamespace(solve=solve))

    async def generate(**kwargs):
        from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides

        return await active_video_overrides.get().token(PAGE)

    with pytest.raises(ConfigurationError, match="configured") as error:
        await video_captcha.generate_video_with_captcha(
            SimpleNamespace(generate_video=generate, _uses_native_characters=lambda: True),
            req=SimpleNamespace(count=1),
            project_id=PROJECT,
            captcha_order="CapSolver",
            root=tmp_path,
        )
    assert "GFLOW_CAPSOLVER_KEY" in error.value.remediation_hint
    solve.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_child_cannot_add_supplied_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("GFLOW_SELFHOST_ROOT", str(tmp_path))
    gate = asyncio.Event()

    async def child():
        await gate.wait()
        native_captcha_submission()
        native_captcha_outcome("accepted")

    with native_captcha_token(TOKEN, project_id=PROJECT, action="VIDEO_GENERATION"):
        assert await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION") == TOKEN
        native_captcha_submission()
        task = asyncio.create_task(child())
    gate.set()
    await task
    assert CaptchaStats(tmp_path).public()["providers"]["supplied"] == {
        "submitted": 1,
        "unknown": 1,
    }


@pytest.mark.parametrize("first", ["supplied", "provider"])
def test_low_level_supplied_and_provider_scopes_are_exclusive(first):
    from gflow_cli.api.native_captcha import native_captcha_provider
    from gflow_cli.errors import ConfigurationError

    supplied = native_captcha_token(TOKEN, project_id=PROJECT, action="VIDEO_GENERATION")
    provider = native_captcha_provider(AsyncMock(), project_id=PROJECT, action="VIDEO_GENERATION")
    outer, inner = (supplied, provider) if first == "supplied" else (provider, supplied)
    with outer:
        with pytest.raises(ConfigurationError, match="combined"):
            with inner:
                pytest.fail("conflicting scopes installed")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "video", "native"])
async def test_private_worker_missing_key_is_typed_before_metadata_or_solver(
    tmp_path, monkeypatch, kind
):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost import image_captcha_policy, native_provider

    module = {
        "image": image_captcha_policy,
        "video": video_captcha_policy,
        "native": native_provider,
    }[kind]
    monkeypatch.setattr(module, "ProviderKeys", lambda root: SimpleNamespace(get=lambda name: None))
    discover = AsyncMock()
    solve = AsyncMock()
    monkeypatch.setattr(module, "discover_site_key", discover)
    monkeypatch.setattr(module, "Solver", lambda: SimpleNamespace(solve=solve))

    async def attempt(override):
        return await override.token(PAGE)

    with pytest.raises(ConfigurationError, match="not configured"):
        if kind == "native":
            with native_provider.native_provider_context(
                {"captchaOrder": "CapSolver"}, PROJECT, "VIDEO_GENERATION", root=tmp_path
            ):
                await take_native_captcha_token_async(PAGE, "VIDEO_GENERATION")
        else:
            policy = (
                image_captcha_policy.run_with_image_captcha_policy
                if kind == "image"
                else video_captcha_policy.run_with_video_captcha_policy
            )
            await policy({"count": 1, "captchaOrder": "CapSolver"}, PROJECT, tmp_path, attempt)
    solve.assert_not_awaited()
    discover.assert_not_awaited()


@pytest.mark.parametrize("required", [True, False])
def test_provider_order_missing_key_cannot_silently_change_explicit_order(required):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost.captcha import configured_provider_keys

    keys = SimpleNamespace(get=lambda name: "synthetic-private-key" if name == "2Captcha" else "")
    if required:
        with pytest.raises(ConfigurationError, match="not configured") as error:
            configured_provider_keys(keys, ["CapSolver", "2Captcha"], require_all=True)
        assert "synthetic-private-key" not in str(error.value)
    else:
        assert configured_provider_keys(keys, ["CapSolver", "2Captcha"], require_all=False) == [
            ("2Captcha", "synthetic-private-key")
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "video"])
async def test_missing_provider_key_refuses_before_generic_client_callback(
    tmp_path, monkeypatch, kind
):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.selfhost import image_captcha_policy

    module = image_captcha_policy if kind == "image" else video_captcha_policy
    monkeypatch.setattr(module, "ProviderKeys", lambda root: SimpleNamespace(get=lambda name: ""))
    attempt = AsyncMock(return_value="should-not-run")
    policy = (
        image_captcha_policy.run_with_image_captcha_policy
        if kind == "image"
        else video_captcha_policy.run_with_video_captcha_policy
    )
    with pytest.raises(ConfigurationError, match="not configured"):
        await policy({"count": 1, "captchaOrder": "CapSolver"}, PROJECT, tmp_path, attempt)
    attempt.assert_not_awaited()
