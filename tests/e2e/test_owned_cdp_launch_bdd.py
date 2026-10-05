"""Original-profile, zero-credit comparison; no fixtures are created or imported.

Explicit private fixture variables are mandatory. Context routing is installed
before bootstrap and permits only known read RPCs, never generation or a solver.
The operator runs this on the authenticated host, not on a copied profile.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import get_settings, reset_settings

scenarios("../features/owned_cdp_launch.feature")

_READ_RPCS = {
    "UpteDb",
    "as29s",
    "o30O0e",
    "nzlxg",
    "Zzl0ze",
}
_BILLABLE_RPCS = {
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


@given(
    "an explicitly opted-in original pro3 profile and existing owned media",
    target_fixture="case",
)
def configured(monkeypatch):
    names = {
        "home": "GFLOW_CLI_E2E_CDP_HOME",
        "profile": "GFLOW_CLI_E2E_CDP_PROFILE",
        "project": "GFLOW_CLI_E2E_CDP_PROJECT",
        "media": "GFLOW_CLI_E2E_CDP_MEDIA",
        "evidence": "GFLOW_CLI_E2E_CDP_EVIDENCE",
    }
    values = {key: os.environ.get(name, "") for key, name in names.items()}
    if not all(values.values()):
        pytest.skip("Explicit original-profile owned-CDP private read fixtures are unset")
    assert values["profile"] == "pro3", "This campaign permits only original pro3"
    assert os.environ.get("GFLOW_CLI_E2E_HOME") == values["home"]
    home = Path(values["home"]).resolve(strict=True)
    profile = (home / "profile_pro3").resolve(strict=True)
    assert profile.is_dir() and profile.is_relative_to(home)
    for name in ("project", "media"):
        UUID(values[name])
    evidence = Path(values["evidence"])
    assert evidence.is_absolute() and not evidence.is_symlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    from gflow_cli.profile_store import read_account_file

    expected_account = read_account_file(profile)
    assert expected_account, "Original profile must already have a recorded account"
    monkeypatch.setenv("GFLOW_CLI_HOME", str(home))
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_CONCURRENCY", "1")
    monkeypatch.setenv("GFLOW_CLI_BROWSER_ENGINE", "patchright")
    monkeypatch.setenv("GFLOW_CLI_FLOW_HOST", "flow.google.com")
    monkeypatch.setenv("GFLOW_CLI_LOCALE", "en-US")
    monkeypatch.setenv("GFLOW_CLI_LEASE_WAIT_SECONDS", "0")
    monkeypatch.delenv("GFLOW_CLI_HAR_PATH", raising=False)
    reset_settings()
    try:
        yield {
            **values,
            "profile_dir": profile,
            "evidence_path": evidence,
            "expected_account": expected_account,
            "runs": [],
            "blocked_billable": [],
            "cookie_imports": 0,
        }
    finally:
        reset_settings()


def _save(case):
    # Persist sanitized diagnostics on failure too; never cookies, signed URLs,
    # debugging endpoints, raw RPC bodies or account identifiers.
    record = {
        "profile": "pro3",
        "generation_attempts": 0,
        "solver_tasks": 0,
        "cookie_imports": case["cookie_imports"],
        "blocked_billable": case["blocked_billable"],
        "runs": case["runs"],
    }
    target = case["evidence_path"]
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)


def _linux_listener_addresses(pid, port):
    """Read actual sockets owned by this process, not a connectability guess."""
    assert sys.platform.startswith("linux"), "Owned socket proof requires the CC Linux host"
    fd_root = Path(f"/proc/{pid}/fd")
    inodes = set()
    for descriptor in fd_root.iterdir():
        try:
            target = descriptor.readlink().as_posix()
        except OSError:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[8:-1])
    addresses = []
    for name, family in (("tcp", socket.AF_INET), ("tcp6", socket.AF_INET6)):
        for line in Path(f"/proc/{pid}/net/{name}").read_text().splitlines()[1:]:
            fields = line.split()
            address, hex_port = fields[1].split(":")
            if fields[3] != "0A" or int(hex_port, 16) != port or fields[9] not in inodes:
                continue
            raw = bytes.fromhex(address)
            if family == socket.AF_INET:
                raw = raw[::-1]
            else:
                raw = b"".join(raw[index : index + 4][::-1] for index in range(0, 16, 4))
            addresses.append(socket.inet_ntop(family, raw))
    return addresses


@when("both shared and standalone browsers read the same account and existing media")
def compare(case, monkeypatch):
    from gflow_cli.api.cdp_launch import CdpLauncher
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.native_credits import read_native_credits
    from gflow_cli.api.transports.native_asset_lookup import lookup_asset
    from gflow_cli.api.transports.ui_automation import UiAutomationTransport
    from gflow_cli.auth.native_identity import read_native_identity
    from gflow_cli.profile_lease import ProfileLease

    current = {}

    async def guard_context(context):
        async def guard(route):
            request = route.request
            parsed = urlsplit(request.url)
            if request.is_navigation_request() and parsed.hostname == "flow.google.com":
                headers = await request.all_headers()
                current["accept_language"] = headers.get("accept-language")
            if "batchexecute" in parsed.path:
                advertised = set(parse_qs(parsed.query).get("rpcids", [""])[0].split(",")) - {""}
                try:
                    form = parse_qs(request.post_data or "")
                    groups = json.loads(form["f.req"][0])
                    assert isinstance(groups, list) and groups
                    requested = set()
                    for group in groups:
                        assert isinstance(group, list) and group
                        for call in group:
                            assert isinstance(call, list) and len(call) >= 2
                            assert isinstance(call[0], str)
                            requested.add(call[0])
                    assert not advertised or advertised == requested
                except (AssertionError, KeyError, TypeError, ValueError):
                    await route.abort()
                    return
                if requested & _BILLABLE_RPCS:
                    case["blocked_billable"].extend(sorted(requested & _BILLABLE_RPCS))
                if not requested or not requested.issubset(_READ_RPCS):
                    await route.abort()
                    return
            elif request.method not in {"GET", "HEAD", "OPTIONS"}:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", guard)

    real_cdp = CdpLauncher.launch

    async def cdp_launch(owner, pw, kwargs):
        context = await real_cdp(owner, pw, kwargs)
        await guard_context(context)
        return context

    monkeypatch.setattr(CdpLauncher, "launch", cdp_launch)
    # Cover both ordinary startup call sites before either one can navigate.
    import patchright.async_api

    real_launch = patchright.async_api.BrowserType.launch_persistent_context

    async def ordinary_launch(browser_type, *args, **kwargs):
        context = await real_launch(browser_type, *args, **kwargs)
        await guard_context(context)
        return context

    monkeypatch.setattr(
        patchright.async_api.BrowserType, "launch_persistent_context", ordinary_launch
    )

    async def refuse_cookie_import(*args, **kwargs):
        case["cookie_imports"] += 1
        raise AssertionError("Original-profile comparison may not import cookies")

    monkeypatch.setattr(patchright.async_api.BrowserContext, "add_cookies", refuse_cookie_import)

    async def no_cookie_preread(client):
        # Original system Chrome must read its own persisted store. No copying
        # or fallback headless context is permitted in this campaign.
        client._preread_flow_cookies = {}

    monkeypatch.setattr(FlowApiClient, "_preread_flow_session_cookies", no_cookie_preread)

    async def inspect(page, owner, expected_viewport):
        await page.goto(
            "https://flow.google.com/project/" + case["project"],
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)")
        identity = await read_native_identity(page)
        assert identity.casefold() == case["expected_account"].casefold()
        credits = await read_native_credits(page)
        asset = await lookup_asset(page, project_id=case["project"], media_id=case["media"])
        assert asset.media_id == case["media"] and asset.project_id == case["project"]
        current.update(
            await page.evaluate("""() => ({
          webdriver: navigator.webdriver === undefined ? 'undefined' : navigator.webdriver,
          language: navigator.language,
          intl_locale: Intl.DateTimeFormat().resolvedOptions().locale,
          viewport: {width: innerWidth, height: innerHeight},
          visibility: document.visibilityState, focus: document.hasFocus()
        })""")
        )
        current.update(
            expected_viewport=expected_viewport,
            identity_matches=True,
            credits=credits.credits,
            owned_media_matches=True,
            media_kind=asset.kind,
        )
        if owner is not None:
            pid, port = owner.process_pid, owner.port
            assert isinstance(pid, int) and isinstance(port, int)
            addresses = _linux_listener_addresses(pid, port)
            assert addresses and set(addresses).issubset({"127.0.0.1", "::1"})
            current.update(process_pid=pid, debugger_port=port, listen_addresses=addresses)

    async def run():
        for surface in ("shared", "standalone"):
            for enabled in (False, True):
                current.clear()
                current.update(surface=surface, launcher="cdp" if enabled else "ordinary")
                case["runs"].append(current.copy())
                monkeypatch.setenv("GFLOW_CLI_CDP_LAUNCH", "true" if enabled else "false")
                reset_settings()
                owner = None
                try:
                    if surface == "shared":
                        client = FlowApiClient(case["profile_dir"], settings=get_settings())
                        async with client:
                            owner = client._cdp_launcher
                            await inspect(client._page, owner, {"width": 1280, "height": 720})
                    else:
                        transport = UiAutomationTransport()
                        try:
                            await transport.setup(case["profile_dir"])
                            owner = transport._cdp_launcher
                            await inspect(transport._page, owner, {"width": 1920, "height": 1080})
                        finally:
                            await transport.teardown()
                    if enabled:
                        assert owner is not None and not owner.process_running
                        pid = current["process_pid"]
                        assert not Path(f"/proc/{pid}").exists(), "Owned Chrome process survived"
                        current.update(process_exited=True, graceful_close=owner.graceful_close)
                    async with ProfileLease(case["profile_dir"]):
                        current["lease_reacquired"] = True
                finally:
                    case["runs"][-1] = current.copy()
                    _save(case)

    asyncio.run(run())


@then("browser policies and loopback ownership are recorded with no mutation or cookie import")
def verify_policies(case):
    assert len(case["runs"]) == 4
    assert case["cookie_imports"] == 0 and case["blocked_billable"] == []
    for run in case["runs"]:
        assert run["identity_matches"] and run["owned_media_matches"]
        assert run["webdriver"] in ("undefined", False)
        assert run["language"] == "en-US" and run["intl_locale"] == "en-US"
        assert run["viewport"] == run["expected_viewport"]
        assert isinstance(run["accept_language"], str)
        assert run["accept_language"].startswith("en-US")
    assert len({run["credits"] for run in case["runs"]}) == 1


@then("each browser exits before the original profile lease can be acquired again")
def verify_cleanup(case):
    for run in case["runs"]:
        assert run["lease_reacquired"]
        if run["launcher"] == "cdp":
            assert run["process_exited"] and run["graceful_close"]


@given(
    "one explicitly reserved pro3 promotion and a private registered MCP connection",
    target_fixture="promotion",
)
def promotion_configured():
    if os.getenv("PRIVATE_CDP_PROMOTION_RESERVED_CASE") != "V6c":
        pytest.skip("Explicit pre-reserved single promotion allowance is unset")
    names = ("MCP_URL", "TOKEN_FILE", "PROFILE", "PROJECT", "MEDIA", "OUTDIR", "EVIDENCE")
    case = {name.lower(): os.getenv("PRIVATE_CDP_PROMOTION_" + name, "") for name in names}
    assert all(case.values()), "All private promotion fixtures are required after reservation"
    assert case["profile"] == "pro3"
    for name in ("project", "media"):
        UUID(case[name])
    url = urlsplit(case["mcp_url"])
    assert (
        url.scheme == "http"
        and url.hostname == "127.0.0.1"
        and url.port == 8843
        and url.path == "/mcp"
        and not url.query
        and not url.fragment
        and url.username is None
        and url.password is None
    ), "Only the existing loopback registered MCP endpoint is allowed"
    token_file = Path(case["token_file"])
    assert token_file.is_file() and not token_file.is_symlink()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    token = token_file.read_text().strip()
    assert token and "\n" not in token
    case["token"] = token
    out = Path(case["outdir"])
    evidence = Path(case["evidence"])
    assert out.is_absolute() and evidence.is_absolute()
    assert not out.is_symlink() and not evidence.is_symlink()
    assert not evidence.exists(), "A prior dispatch checkpoint exists; inspect it, never replay"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    case["checkpoint"] = {
        "reserved_case": "V6c",
        "profile": "pro3",
        "video_attempts": 1,
        "solver_tasks": 0,
        "tool_calls": 0,
        "phase": "configured",
    }
    return case


def _promotion_checkpoint(case):
    path = Path(case["evidence"])
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(case["checkpoint"], stream, indent=2)
    temporary.chmod(0o600)
    temporary.replace(path)


@when("the native promotion tool is invoked exactly once without solver or retry controls")
def promotion_invoke(promotion):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def invoke():
        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + promotion["token"]},
            timeout=900,
            trust_env=False,
        ) as http:
            async with streamable_http_client(promotion["mcp_url"], http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    registered = await session.list_tools()
                    matches = [
                        tool
                        for tool in registered.tools
                        if tool.name == "gflow_upscale_native_video"
                    ]
                    assert len(matches) == 1, "Native promotion tool is not registered"
                    arguments = {
                        "profile": "pro3",
                        "project": promotion["project"],
                        "media_id": promotion["media"],
                        "resolution": "1080p",
                        "out_dir": promotion["outdir"],
                    }
                    properties = matches[0].inputSchema.get("properties", {})
                    assert set(arguments).issubset(properties), (
                        "Registered promotion schema differs"
                    )
                    assert "captcha_retry" not in arguments and "captcha_order" not in arguments
                    # Exclusive durable marker is the no-replay gate; it exists
                    # before the only mutating tool call, including timeouts.
                    descriptor = os.open(
                        promotion["evidence"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                    )
                    promotion["checkpoint"].update(phase="dispatching", tool_calls=1, unknown=True)
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump(promotion["checkpoint"], stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    result = await asyncio.wait_for(
                        session.call_tool(matches[0].name, arguments), timeout=900
                    )
                    value = result.structured_content
                    if value is None:
                        value = json.loads(
                            next(item.text for item in result.content if item.type == "text")
                        )
                    promotion["checkpoint"].update(
                        phase="response_received",
                        response=value,
                        mcp_error=result.is_error is True,
                    )
                    error = value.get("error") if isinstance(value, dict) else None
                    if isinstance(error, dict) and error.get("type") in {
                        "https://gflow-cli.dev/errors/waf-rejection",
                        "https://gflow-cli.dev/errors/native-quota",
                    }:
                        promotion["checkpoint"].update(
                            phase="google_explicitly_refused",
                            unknown=False,
                            refusal_type=error["type"],
                        )
                    _promotion_checkpoint(promotion)
                    if (
                        result.is_error is True
                        or not isinstance(value, dict)
                        or value.get("status") != "ok"
                    ):
                        pytest.fail(
                            "Promotion was not accepted; inspect the retained private response",
                            pytrace=False,
                        )
                    promotion["value"] = value

    try:
        asyncio.run(invoke())
    except BaseException as error:
        if Path(promotion["evidence"]).exists():
            promotion["checkpoint"]["error_class"] = type(error).__name__
            _promotion_checkpoint(promotion)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        pytest.fail(
            "Single promotion did not validate; inspect checkpoint without replay", pytrace=False
        )


@then("one new native 1080p MP4 decodes with preserved source identity")
def promotion_validated(promotion):
    value = promotion["value"]
    assert value["type"] == "video_promotion_result"
    assert value["source_media_id"] == promotion["media"]
    assert value["project_id"] == promotion["project"] and value["target_resolution"] == "1080p"
    assert len(value["results"]) == 1
    output = value["results"][0]
    UUID(output["media_id"])
    assert output["media_id"] != promotion["media"]
    path = Path(output["local_path"]).resolve(strict=True)
    assert path.is_file() and path.is_relative_to(Path(promotion["outdir"]).resolve(strict=True))
    assert 0 < path.stat().st_size <= 1024 * 1024 * 1024
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert probe.returncode == 0
    measured = json.loads(probe.stdout)
    videos = [stream for stream in measured["streams"] if stream["codec_type"] == "video"]
    assert len(videos) == 1
    dimensions = (videos[0]["width"], videos[0]["height"])
    assert sorted(dimensions) == [1080, 1920]
    assert dimensions == (output["width"], output["height"])
    duration = float(measured["format"]["duration"])
    assert 7 <= duration <= 9
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert decoded.returncode == 0, "Promoted MP4 did not decode"
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    promotion["checkpoint"].update(
        phase="accepted_and_decoded",
        unknown=False,
        dimensions=list(dimensions),
        duration=duration,
        sha256=digest,
    )
    _promotion_checkpoint(promotion)
