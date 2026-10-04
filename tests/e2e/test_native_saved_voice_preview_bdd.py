"""Opt-in one-shot native TTS preview and owned playback proof."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_captcha import native_captcha_token
from gflow_cli.api.native_extension import _read_native
from gflow_cli.api.transports import native_voices
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.selfhost.captcha import CaptchaStats, Solver
from gflow_cli.selfhost.captcha_routes import provider_keys
from gflow_cli.selfhost.config import Settings

scenarios("../features/native_saved_voice_preview.feature")


def require(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


@given("an explicitly reserved real audio preview", target_fixture="case")
def configured(monkeypatch):
    if os.getenv("GFLOW_CLI_E2E_SAVED_VOICE_PREVIEW") != "1":
        pytest.skip("Explicit real audio preview authorization and reservation required")
    fixture = Path(os.environ["GFLOW_CLI_E2E_SAVED_VOICE_FIXTURE"])
    data = json.loads(fixture.read_text())
    require(data["phase"] == "reserved", "One-shot reserved preview fixture required")
    monkeypatch.setenv("GFLOW_CLI_HOME", os.environ["GFLOW_CLI_E2E_HOME"])
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    reset_settings()
    return {"fixture": fixture, "data": data, "preview_requests": 0}


@when("one short saved voice is created and its playback is looked up")
def create_and_read(case, monkeypatch):
    original = native_voices._rpc
    stats = CaptchaStats(Settings.environment().root)
    provider = case["data"].get("captcha_provider")

    def record(**updates):
        case["data"].update(updates)
        temporary = case["fixture"].with_suffix(".tmp")
        temporary.write_text(json.dumps(case["data"]))
        temporary.chmod(0o600)
        os.replace(temporary, case["fixture"])

    async def counted(page, project, rpc, args):
        if rpc == native_voices.PREVIEW_RPC:
            case["preview_requests"] += 1
            require(case["preview_requests"] == 1, "No preview replay is authorized")
            record(phase="before_preview_submission", generation_submitted=True)
            if provider:
                stats.record(provider, "submitted")
        return await original(page, project, rpc, args)

    monkeypatch.setattr(native_voices, "_rpc", counted)

    async def run():
        data = case["data"]
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir(data["profile"]), headless=False
        ) as client:
            before = await client.list_saved_voices(data["project"])
            record(original_voices=[v["ref"] for v in before["voices"]])
            try:
                record(credits_before=(await client.get_credits()).credits)
            except Exception as error:
                record(credits_before=None, credit_read_error=type(error).__name__)
            try:
                token = None
                if provider:
                    require(
                        provider == "CapSolver",
                        "Only the configured CapSolver alternative is authorized",
                    )
                    page = await client._checkout_page()
                    try:
                        await page.wait_for_function(
                            "() => Array.from(document.scripts).some("
                            "s => s.src.includes('/recaptcha/enterprise.js?'))",
                            timeout=15000,
                        )
                        sitekey = await page.evaluate(
                            "() => new URL(Array.from(document.scripts).find("
                            "s => s.src.includes('/recaptcha/enterprise.js?')).src)"
                            ".searchParams.get('render')"
                        )
                        require(
                            isinstance(sitekey, str) and bool(sitekey),
                            "Fresh native Enterprise site key required",
                        )
                        stats.record(provider, "solveStarted")
                        try:
                            solution = await Solver().solve(
                                provider,
                                provider_keys().get(provider)
                                or os.environ.get("GFLOW_CAPSOLVER_KEY", ""),
                                page.url,
                                sitekey,
                                "AUDIO_GENERATION",
                            )
                            token = solution.token
                            stats.record(provider, "solved")
                            record(solver_solved=True)
                        except Exception:
                            stats.record(provider, "solveFailed")
                            raise
                    finally:
                        client._checkin_page(page)
                with (
                    native_captcha_token(
                        token, project_id=data["project"], action="AUDIO_GENERATION"
                    )
                    if token
                    else nullcontext()
                ):
                    voice = await client.create_saved_voice(
                        project_id=data["project"],
                        display_name=data["name"],
                        preset_voice="Charon",
                        dialog="This is a short gflow audio preview.",
                        performance="Calm, clear, and friendly.",
                    )
                if provider:
                    stats.record(provider, "accepted")
                record(phase="created", voice=voice)
                detail = await client.get_saved_voice(data["project"], voice["ref"])
                record(detail=detail)
                case["detail"] = detail
            except Exception as error:
                if provider and case["preview_requests"]:
                    stats.record(
                        provider,
                        "rejected"
                        if type(error).__name__ in {"WafRejectionError", "ContentPolicyError"}
                        else "unknown",
                    )
                record(
                    phase="failed",
                    exception_class=type(error).__name__,
                    generation_submitted=case["preview_requests"] == 1,
                    outcome_unknown=type(error).__name__ == "VoiceMutationUnknownError",
                    explicit_refusal=type(error).__name__
                    in {"WafRejectionError", "ContentPolicyError"},
                    preview_requests=case["preview_requests"],
                )
                case["error"] = type(error).__name__
            finally:
                try:
                    record(credits_after=(await client.get_credits()).credits)
                except Exception as error:
                    record(credits_after=None, credit_read_error=type(error).__name__)
                page = await client._checkout_page()
                try:
                    models = await _read_native(page, "HTrJv", [], data["project"])
                    credits = await _read_native(page, "nzlxg", [], data["project"])
                    target = case["fixture"].parent / "pro3-current-image-models.private"
                    target.write_text(json.dumps({"models": models, "credits": credits}))
                    target.chmod(0o600)
                finally:
                    client._checkin_page(page)

    asyncio.run(asyncio.wait_for(run(), 180))


@then("fresh owned audio bytes decode and no second preview is submitted")
def verify(case):
    require(case["preview_requests"] == 1, "Expected one explicit preview submission")
    require("error" not in case, "Native audio preview failed: " + case.get("error", ""))
    detail = case["detail"]
    data = case["data"]
    require(
        detail["ref"] == data["voice"]["ref"]
        and detail["project_id"] == data["project"]
        and detail["workflow_id"] == data["voice"]["workflow_id"],
        "Playback lookup must retain acknowledged owned scope",
    )
    require(bool(detail.get("audio_url")), "Fresh owned playback URL is unavailable")
    url = detail["audio_url"]
    parsed = urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.hostname == "flow-content.google"
        and parsed.path.startswith("/audio/")
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443),
        "Owned audio playback host is not the measured native CDN",
    )
    path = case["fixture"].parent / "saved-voice-preview.audio"
    size = 0
    with httpx.stream("GET", url, timeout=30, follow_redirects=False, trust_env=False) as response:
        require(response.status_code == 200, "Owned audio download failed")
        with path.open("xb") as output:
            path.chmod(0o600)
            for chunk in response.iter_bytes():
                size += len(chunk)
                require(size <= 10 * 1024 * 1024, "Short audio preview exceeded the byte bound")
                output.write(chunk)
    require(size > 1024, "Owned audio preview is empty")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        timeout=30,
    )
    require(result.returncode == 0, "Owned audio preview did not decode")
    case["data"].update(phase="verified", decoded=True, preview_requests=1, audio_bytes=size)
    temporary = case["fixture"].with_suffix(".tmp")
    temporary.write_text(json.dumps(case["data"]))
    temporary.chmod(0o600)
    os.replace(temporary, case["fixture"])
