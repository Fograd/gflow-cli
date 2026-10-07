"""Free recovery proof using a retained generic clip, never a new extension."""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_extension import (
    NativeExtensionStarted,
    download_native_extension,
    wait_native_extension,
)
from gflow_cli.config import get_settings, reset_settings

scenarios("../features/native_extension_recovery.feature")


@given("an explicitly configured original pro3 retained video", target_fixture="case")
def configured(monkeypatch):
    names = ("HOME", "PROJECT", "MEDIA", "WORKFLOW", "OUTPUT", "EVIDENCE")
    values = {key.lower(): os.environ.get("GFLOW_CLI_E2E_EXT_RECOVERY_" + key) for key in names}
    if not all(values.values()):
        pytest.skip("Explicit original-profile retained-video fixture required")
    home = Path(values["home"]).resolve(strict=True)
    assert os.environ.get("GFLOW_CLI_E2E_HOME") == str(home)
    for key in ("project", "media", "workflow"):
        UUID(values[key])
    profile = home / "profile_pro3"
    assert profile.is_dir()
    from gflow_cli.profile_store import read_account_file

    expected = read_account_file(profile)
    assert expected
    monkeypatch.setenv("GFLOW_CLI_HOME", str(home))
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    monkeypatch.setenv("GFLOW_CLI_CDP_LAUNCH", "false")
    reset_settings()
    assert get_settings().cdp_launch is False
    yield {**values, "expected_account": expected, "blocked": [], "read_rpcs": []}
    reset_settings()


@when("extension recovery polls and downloads with all mutations blocked")
def recover(case, monkeypatch):
    import patchright.async_api

    from gflow_cli.api.native_credits import read_native_credits
    from gflow_cli.auth.native_identity import read_native_identity

    launch = patchright.async_api.BrowserType.launch_persistent_context

    async def guarded_launch(owner, *args, **kwargs):
        context = await launch(owner, *args, **kwargs)

        async def guard(route):
            request = route.request
            if "batchexecute" in urlsplit(request.url).path:
                rpcs = set()
                try:
                    groups = json.loads(parse_qs(request.post_data or "")["f.req"][0])
                    rpcs = {call[0] for group in groups for call in group}
                    assert rpcs and rpcs.issubset({"UpteDb", "as29s", "o30O0e", "nzlxg", "Zzl0ze"})
                except (KeyError, TypeError, ValueError, AssertionError):
                    case["blocked"].extend(sorted(rpcs) or ["malformed-rpc"])
                    await route.abort()
                    return
                case["read_rpcs"].extend(sorted(rpcs))
            elif request.method not in {"GET", "HEAD", "OPTIONS"}:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", guard)
        return context

    monkeypatch.setattr(
        patchright.async_api.BrowserType, "launch_persistent_context", guarded_launch
    )

    async def no_import(*args, **kwargs):
        raise AssertionError("Original profile cookies may not be imported")

    async def no_preread(client):
        client._preread_flow_cookies = {}

    monkeypatch.setattr(patchright.async_api.BrowserContext, "add_cookies", no_import)
    monkeypatch.setattr(FlowApiClient, "_preread_flow_session_cookies", no_preread)
    monkeypatch.setattr("gflow_cli.api.recaptcha.TokenMinter.mint", no_import)
    monkeypatch.setattr(FlowApiClient, "extend_native_video", no_import)

    async def run():
        async with FlowApiClient(
            profile_dir=get_settings().profile_subdir("pro3"), headless=False
        ) as client:
            page = await client._checkout_page()
            try:
                await page.goto(
                    "https://flow.google.com/project/" + case["project"],
                    wait_until="domcontentloaded",
                )
                identity = await read_native_identity(page)
                assert identity.casefold() == case["expected_account"].casefold()
                before = await read_native_credits(page)
            finally:
                client._checkin_page(page)
            # This is a known existing generic output used solely to exercise recovery.
            started = NativeExtensionStarted(
                case["project"], case["media"], (case["media"],), (case["workflow"],)
            )
            records = await wait_native_extension(client, started, timeout_s=30)
            outputs = await download_native_extension(
                client, started, records, Path(case["output"])
            )
            page = await client._checkout_page()
            try:
                after = await read_native_credits(page)
            finally:
                client._checkin_page(page)
        assert before.credits == after.credits
        output = outputs[0]
        assert (output.media_id, output.project_id, output.workflow_id) == (
            case["media"],
            case["project"],
            case["workflow"],
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(output.path), "-f", "null", "-"], check=True
        )
        case["result"] = {
            "width": output.width,
            "height": output.height,
            "sha256": output.sha256,
            "bytes": output.bytes,
            "credits_before": before.credits,
            "credits_after": after.credits,
            "identity_matches": True,
            "generation_submissions": 0,
            "solver_tasks": 0,
            "read_rpcs": sorted(set(case["read_rpcs"])),
            "blocked_background_rpcs": sorted(set(case["blocked"])),
            "proof": "existing generic clip recovery only; no new extension",
        }

    asyncio.run(asyncio.wait_for(run(), 240))


@then("the retained MP4 validates and no campaign allowance is consumed")
def verified(case):
    assert (case["result"]["width"], case["result"]["height"]) == (1280, 720)
    assert not set(case["blocked"]) & {
        "MZZa6b",
        "fZytfe",
        "jIps6",
        "p0UkFb",
        "no0P6",
        "YhhmEf",
        "eb1hJf",
        "nprQif",
        "ogiZ0b",
        "aGxPZc",
        "iVbZqd",
    }
    assert "as29s" in case["result"]["read_rpcs"]
    Path(case["evidence"]).write_text(json.dumps(case["result"], indent=2))
