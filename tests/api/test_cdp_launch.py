"""Owned CDP startup must preserve options, original sessions, and process ownership."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api import cdp_launch
from gflow_cli.config import BrowserEngine
from gflow_cli.errors import AuthExpiredError, ConfigurationError, ProfileAccessError, SecurityError

_BROWSER_ID = "ba39b5bb-1a37-4675-b43f-6290a3f935df"


@pytest.fixture
def launch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(cdp_launch.sys, "platform", "darwin")
    home = tmp_path / "home"
    profile = home / "profile_pro3"
    profile.mkdir(parents=True, mode=0o700)
    home.chmod(0o700)
    page = MagicMock()
    page.set_viewport_size = AsyncMock()
    context = MagicMock()
    context.pages = [page]
    context.new_page = AsyncMock(return_value=page)
    context.new_cdp_session = AsyncMock(
        return_value=SimpleNamespace(
            send=AsyncMock(),
            detach=AsyncMock(),
        )
    )
    context.set_extra_http_headers = AsyncMock()
    context.cookies = AsyncMock(
        return_value=[
            {
                "name": "__Secure-next-auth.session-token",
                "value": "private",
                "domain": "flow.google.com",
                "secure": True,
                "expires": time.time() + 3600,
            }
        ]
    )
    browser = SimpleNamespace(
        contexts=[context],
        close=AsyncMock(),
        new_browser_cdp_session=AsyncMock(return_value=SimpleNamespace(send=AsyncMock())),
    )
    pw = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser)))
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 918273
    process.poll.return_value = None
    process.wait.return_value = 0
    monkeypatch.setattr(
        cdp_launch,
        "get_settings",
        lambda: SimpleNamespace(
            browser_engine=BrowserEngine.PATCHRIGHT,
            flow_host="auto",
        ),
    )
    monkeypatch.setattr(cdp_launch, "_system_chrome", lambda: "/installed/google-chrome")
    spawn = MagicMock(return_value=process)
    monkeypatch.setattr(cdp_launch, "_spawn_process", spawn)
    monkeypatch.setattr(cdp_launch, "_group_running", lambda _pid: False)
    endpoint = AsyncMock(return_value=f"ws://127.0.0.1:44321/devtools/browser/{_BROWSER_ID}")
    monkeypatch.setattr(cdp_launch, "_wait_endpoint", endpoint)
    kwargs = {
        "user_data_dir": str(profile),
        "headless": False,
        "channel": "chrome",
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-US",
        "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
        "ignore_default_args": ["--enable-automation", "--no-sandbox"],
        "args": [
            "--password-store=basic",
            "--disable-blink-features=AutomationControlled",
            "--restore-last-session",
            "--window-position=-30000,-30000",
        ],
    }
    return SimpleNamespace(
        home=home,
        profile=profile,
        page=page,
        context=context,
        browser=browser,
        pw=pw,
        process=process,
        spawn=spawn,
        kwargs=kwargs,
        endpoint=endpoint,
    )


@pytest.mark.asyncio
async def test_launch_preserves_profile_options_and_configures_new_pages(launch_env) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    ctx = await owner.launch(env.pw, env.kwargs)
    cmd = env.spawn.call_args.args[0]
    assert f"--user-data-dir={env.profile}" in cmd
    assert "--remote-debugging-address=127.0.0.1" in cmd
    assert "--remote-debugging-port=0" in cmd
    assert "--password-store=basic" in cmd
    assert "--disable-blink-features=AutomationControlled" in cmd
    assert "--restore-last-session" in cmd
    assert not any(arg.startswith("--remote-allow-origins") for arg in cmd)
    env.page.set_viewport_size.assert_awaited_once_with({"width": 1280, "height": 720})
    env.context.set_extra_http_headers.assert_awaited_once_with(env.kwargs["extra_http_headers"])
    env.context.new_cdp_session.return_value.send.assert_awaited_once_with(
        "Emulation.setLocaleOverride",
        {"locale": "en-US"},
    )
    await ctx.new_page()
    assert env.page.set_viewport_size.await_count == 2
    env.context.close.assert_not_called()
    env.context.add_cookies.assert_not_called()
    await ctx.close()
    await owner.reap()
    env.browser.close.assert_not_called()
    env.browser.new_browser_cdp_session.return_value.send.assert_awaited_once_with("Browser.close")
    assert owner.graceful_close
    assert not owner.process_running


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"headless": True},
        {"channel": None},
        {"record_har_path": "private.har"},
        {"record_video_dir": "videos"},
        {"proxy": {"server": "http://localhost:8000"}},
        {"no_viewport": True},
        {"locale": "en-US\n--no-sandbox"},
        {"viewport": {"width": 0, "height": 720}},
        {"args": ["--no-sandbox"]},
        {"args": ["--disable-setuid-sandbox"]},
        {"args": ["--remote-debugging-port=1234"]},
        {"args": ["--remote-allow-origins=*"]},
        {"args": ["--user-data-dir=/other"]},
        {"args": ["--password-store=gnome"]},
        {"args": ["--load-extension=/unsafe"]},
        {"args": ["--disable-extensions-except=/unsafe"]},
        {"args": ["--disable-blink-features=AutomationControlled,WebSecurity"]},
        {"ignore_default_args": [{}]},
        {"extra_http_headers": {5: "invalid"}},
    ],
)
async def test_invalid_options_fail_before_spawn(launch_env, extra) -> None:
    env = launch_env
    with pytest.raises(ConfigurationError):
        await cdp_launch.CdpLauncher(env.home).launch(env.pw, env.kwargs | extra)
    env.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_engine_fails_before_spawn(launch_env, monkeypatch) -> None:
    monkeypatch.setattr(
        cdp_launch,
        "get_settings",
        lambda: SimpleNamespace(
            browser_engine=BrowserEngine.PLAYWRIGHT,
        ),
    )
    with pytest.raises(ConfigurationError):
        await cdp_launch.CdpLauncher(launch_env.home).launch(launch_env.pw, launch_env.kwargs)
    launch_env.spawn.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["outside", "symlink", "writable", "missing"])
async def test_unsafe_profiles_fail_before_spawn(launch_env, tmp_path, kind) -> None:
    env = launch_env
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    if kind == "symlink":
        path = env.home / "profile_link"
        path.symlink_to(outside, target_is_directory=True)
    elif kind == "writable":
        path = env.profile
        path.chmod(0o777)
    elif kind == "missing":
        path = env.home / "missing"
    else:
        path = outside
    with pytest.raises(SecurityError):
        await cdp_launch.CdpLauncher(env.home).launch(
            env.pw,
            env.kwargs
            | {
                "user_data_dir": str(path),
            },
        )
    env.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_missing_default_context_never_creates_new_context(launch_env) -> None:
    env = launch_env
    env.browser.contexts = []
    env.browser.new_context = AsyncMock()
    owner = cdp_launch.CdpLauncher(env.home)
    with pytest.raises(ConfigurationError):
        await owner.launch(env.pw, env.kwargs)
    env.browser.new_context.assert_not_called()
    env.browser.new_browser_cdp_session.return_value.send.assert_awaited_once_with("Browser.close")
    assert not owner.process_running


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["absent", "expired", "foreign", "probe_error"])
async def test_original_session_is_required_without_cookie_import(launch_env, kind) -> None:
    env = launch_env
    if kind == "probe_error":
        env.context.cookies.side_effect = RuntimeError("private browser payload")
    elif kind == "absent":
        env.context.cookies.return_value = []
    elif kind == "foreign":
        env.context.cookies.return_value[0]["domain"] = "evil.invalid"
    else:
        env.context.cookies.return_value[0]["expires"] = time.time() - 1
    owner = cdp_launch.CdpLauncher(env.home)
    with pytest.raises(AuthExpiredError):
        await owner.launch(env.pw, env.kwargs)
    env.context.add_cookies.assert_not_called()
    assert not owner.process_running


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["readiness", "attach", "viewport", "locale", "headers"])
async def test_every_post_spawn_failure_reaps_owned_process(launch_env, step) -> None:
    env = launch_env
    operation = {
        "readiness": env.endpoint,
        "attach": env.pw.chromium.connect_over_cdp,
        "viewport": env.page.set_viewport_size,
        "locale": env.context.new_cdp_session.return_value.send,
        "headers": env.context.set_extra_http_headers,
    }[step]
    operation.side_effect = RuntimeError("private payload")
    owner = cdp_launch.CdpLauncher(env.home)
    with pytest.raises(ConfigurationError) as caught:
        await owner.launch(env.pw, env.kwargs)
    assert "private payload" not in str(caught.value)
    assert not owner.process_running


@pytest.mark.asyncio
async def test_cancelled_startup_reaps_before_propagating(launch_env) -> None:
    env = launch_env
    waiting = asyncio.Event()

    async def wait_forever(*_args):
        waiting.set()
        await asyncio.Event().wait()

    env.endpoint.side_effect = wait_forever
    owner = cdp_launch.CdpLauncher(env.home)
    task = asyncio.create_task(owner.launch(env.pw, env.kwargs))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not owner.process_running


@pytest.mark.asyncio
async def test_cancelled_reap_keeps_cleanup_alive(launch_env) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    await owner.launch(env.pw, env.kwargs)
    closing = asyncio.Event()
    release = asyncio.Event()

    async def close(*_args):
        closing.set()
        await release.wait()

    env.browser.new_browser_cdp_session.return_value.send.side_effect = close
    task = asyncio.create_task(owner.reap())
    await closing.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not owner.process_running


@pytest.mark.asyncio
async def test_readiness_rejects_stale_and_accepts_fresh_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "DevToolsActivePort"
    path.write_text(f"44321\n/devtools/browser/{_BROWSER_ID}\n")
    path.chmod(0o600)
    before = cdp_launch._file_snapshot(path)
    process = MagicMock()
    process.poll.return_value = None
    monkeypatch.setattr(cdp_launch, "_STARTUP_TIMEOUT_S", 0.03)
    with pytest.raises(ConfigurationError):
        await cdp_launch._wait_endpoint(path, process, before)
    before = cdp_launch._file_snapshot(path)
    path.write_text(f"44322\n/devtools/browser/{_BROWSER_ID}\n")
    assert await cdp_launch._wait_endpoint(path, process, before) == (
        f"ws://127.0.0.1:44322/devtools/browser/{_BROWSER_ID}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contents",
    [
        "65536\n/devtools/browser/ba39b5bb-1a37-4675-b43f-6290a3f935df\n",
        "44321\nws://evil.invalid/browser/ba39b5bb-1a37-4675-b43f-6290a3f935df\n",
        "44321\n/devtools/browser/not-a-uuid\n",
        "44321\n/devtools/browser/ba39b5bb-1a37-4675-b43f-6290a3f935df?secret\n",
    ],
)
async def test_readiness_rejects_invalid_endpoint(tmp_path, contents) -> None:
    path = tmp_path / "DevToolsActivePort"
    path.write_text(contents)
    path.chmod(0o600)
    process = MagicMock()
    process.poll.return_value = None
    with pytest.raises(ConfigurationError):
        await cdp_launch._wait_endpoint(path, process, None)


@pytest.mark.asyncio
async def test_readiness_symlink_rejected_without_reading_target(tmp_path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("private")
    path = tmp_path / "DevToolsActivePort"
    path.symlink_to(secret)
    with pytest.raises(SecurityError):
        cdp_launch._file_snapshot(path)


@pytest.mark.asyncio
async def test_failed_reap_can_retry_with_owner_and_lease_retained(launch_env, monkeypatch) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    await owner.launch(env.pw, env.kwargs)
    reap = MagicMock(side_effect=[ConfigurationError("process exit unknown"), False])
    monkeypatch.setattr(cdp_launch, "_reap_process", reap)
    with pytest.raises(ConfigurationError):
        await owner.reap()
    assert owner.process_running
    await owner.reap()
    assert not owner.process_running
    assert not owner.graceful_close
    assert reap.call_count == 2


@pytest.mark.asyncio
async def test_process_access_denial_retains_typed_error(launch_env) -> None:
    env = launch_env
    env.spawn.side_effect = PermissionError("private path")
    owner = cdp_launch.CdpLauncher(env.home)
    with pytest.raises(ProfileAccessError) as caught:
        await owner.launch(env.pw, env.kwargs)
    assert "private path" not in str(caught.value)
    assert not owner.process_running


@pytest.mark.asyncio
async def test_graceful_close_failure_is_forced_and_not_reported_graceful(launch_env) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    ctx = await owner.launch(env.pw, env.kwargs)
    env.browser.new_browser_cdp_session.return_value.send.side_effect = RuntimeError("private")
    await ctx.close()
    assert not owner.graceful_close
    assert not owner.process_running


def test_process_cleanup_escalates_only_owned_tree(monkeypatch) -> None:
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 51937
    process.poll.return_value = None
    wait = MagicMock(side_effect=[False, False, True])
    stop = MagicMock()
    monkeypatch.setattr(cdp_launch, "_wait_process", wait)
    monkeypatch.setattr(cdp_launch, "_signal_process", stop)
    assert not cdp_launch._reap_process(process, True)
    assert stop.call_args_list[0].args == (process,)
    assert stop.call_args_list[0].kwargs == {"force": False}
    assert stop.call_args_list[1].kwargs == {"force": True}


def test_process_cleanup_failure_preserves_live_handle(monkeypatch) -> None:
    process = MagicMock(spec=subprocess.Popen)
    process.poll.return_value = None
    monkeypatch.setattr(cdp_launch, "_wait_process", lambda *_args: False)
    monkeypatch.setattr(cdp_launch, "_signal_process", MagicMock())
    with pytest.raises(ConfigurationError, match="lease held"):
        cdp_launch._reap_process(process, False)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process group lifecycle")
@pytest.mark.asyncio
async def test_real_local_process_group_reaped_without_browser_or_network(tmp_path) -> None:
    owner = cdp_launch.CdpLauncher(tmp_path)
    owner._process = cdp_launch._spawn_process([sys.executable, "-c", "import time;time.sleep(60)"])
    process = owner._process
    assert owner.process_running
    await owner.reap()
    assert process.poll() is not None
    assert not owner.process_running
    await owner.reap()


@pytest.mark.asyncio
async def test_migrated_original_google_session_does_not_need_legacy_cookie(launch_env) -> None:
    env = launch_env
    env.context.cookies.return_value[0].update(name="SAPISID", domain=".google.com")
    owner = cdp_launch.CdpLauncher(env.home)
    await owner.launch(env.pw, env.kwargs)
    env.context.add_cookies.assert_not_called()
    await owner.reap()


@pytest.mark.asyncio
@pytest.mark.parametrize("actual", ["owner@example.invalid", "other@example.invalid", None])
async def test_native_identity_binds_original_recorded_account(
    launch_env, monkeypatch, actual
) -> None:
    env = launch_env
    page = SimpleNamespace(
        url="https://flow.google.com/project/owned", wait_for_function=AsyncMock()
    )
    monkeypatch.setattr(
        "gflow_cli.profile_store.read_account_file", lambda _: "owner@example.invalid"
    )
    read = (
        AsyncMock(return_value=actual)
        if actual is not None
        else AsyncMock(side_effect=ValueError("no identity"))
    )
    monkeypatch.setattr("gflow_cli.auth.native_identity.read_native_identity", read)
    owner = cdp_launch.CdpLauncher(env.home)
    if actual == "owner@example.invalid":
        await owner.verify_native_identity(page, env.profile)
    else:
        with pytest.raises((SecurityError, AuthExpiredError)):
            await owner.verify_native_identity(page, env.profile)
    env.context.add_cookies.assert_not_called()


@pytest.mark.asyncio
async def test_standalone_locale_supplies_accept_language(launch_env) -> None:
    env = launch_env
    env.kwargs.pop("extra_http_headers")
    owner = cdp_launch.CdpLauncher(env.home)
    await owner.launch(env.pw, env.kwargs)
    env.context.set_extra_http_headers.assert_awaited_once_with({"Accept-Language": "en-US"})
    await owner.reap()


@pytest.mark.asyncio
async def test_cdp_auto_refuses_labs_before_any_generation(launch_env) -> None:
    env = launch_env
    page = SimpleNamespace(url="https://labs.google/fx/tools/flow")
    owner = cdp_launch.CdpLauncher(env.home)
    with pytest.raises(AuthExpiredError):
        await owner.verify_native_identity(page, env.profile)


@pytest.mark.parametrize("state,expected", [("Z", False), ("X", False), ("S", True)])
def test_lxc_exited_group_members_do_not_hold_profile(
    tmp_path, monkeypatch, state, expected
) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    member = proc / "12345"
    member.mkdir()
    (member / "stat").write_text(f"12345 (chrome helper) {state} 1 999 0 0")
    real_path = Path
    monkeypatch.setattr(
        cdp_launch, "Path", lambda value: proc if value == "/proc" else real_path(value)
    )
    assert bool(cdp_launch._linux_group_live_members(999)) is expected


def test_scope_cleanup_requires_empty_inactive_owned_control_group(monkeypatch) -> None:
    unit = "gflow-cdp-ba39b5bb-1a37-4675-b43f-6290a3f935df.scope"
    calls = MagicMock(
        side_effect=[
            SimpleNamespace(stdout=b"", returncode=0),
            SimpleNamespace(stdout=b"", returncode=0),
            SimpleNamespace(stdout=b"inactive\n", returncode=0),
        ]
    )
    monkeypatch.setattr(cdp_launch.subprocess, "run", calls)
    cdp_launch._stop_owned_scope(unit)
    assert calls.call_args_list[1].args[0] == ["/usr/bin/systemctl", "--user", "stop", unit]


def test_scope_cleanup_cannot_stop_an_unrelated_service(monkeypatch) -> None:
    calls = MagicMock()
    monkeypatch.setattr(cdp_launch.subprocess, "run", calls)
    with pytest.raises(SecurityError):
        cdp_launch._stop_owned_scope("gflow-mcp.service")
    calls.assert_not_called()


def test_scope_owner_remains_live_until_scope_cleanup_is_proven(tmp_path) -> None:
    owner = cdp_launch.CdpLauncher(tmp_path)
    owner._process = MagicMock()
    owner._process.poll.return_value = 0
    owner._scope_name = "gflow-cdp-ba39b5bb-1a37-4675-b43f-6290a3f935df.scope"
    assert owner.process_running
    owner._reaped = True
    assert not owner.process_running


@pytest.mark.parametrize("populated", ["0", "1"])
def test_scope_cleanup_checks_real_nonempty_control_group(tmp_path, monkeypatch, populated) -> None:
    unit = "gflow-cdp-ba39b5bb-1a37-4675-b43f-6290a3f935df.scope"
    root = tmp_path / "cgroups"
    group = root / "user.scope" / unit
    group.mkdir(parents=True)
    (group / "cgroup.events").write_text(f"populated {populated}\nfrozen 0\n")
    calls = MagicMock(
        side_effect=[
            SimpleNamespace(stdout=("/user.scope/" + unit).encode(), returncode=0),
            SimpleNamespace(stdout=b"", returncode=0),
            SimpleNamespace(stdout=b"inactive\n", returncode=0),
        ]
    )
    monkeypatch.setattr(cdp_launch.subprocess, "run", calls)
    real_path = Path
    monkeypatch.setattr(
        cdp_launch, "Path", lambda value: root if value == "/sys/fs/cgroup" else real_path(value)
    )
    if populated == "1":
        with pytest.raises(ConfigurationError):
            cdp_launch._stop_owned_scope(unit)
    else:
        cdp_launch._stop_owned_scope(unit)


@pytest.mark.asyncio
async def test_rejected_cdp_browser_never_receives_close_command(launch_env, monkeypatch) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    owner._process = env.process
    owner._browser = env.browser
    owner._browser_owned = False
    owner._scope_name = "gflow-cdp-ba39b5bb-1a37-4675-b43f-6290a3f935df.scope"
    stopped = MagicMock()
    monkeypatch.setattr(cdp_launch, "_stop_owned_scope", stopped)
    monkeypatch.setattr(cdp_launch, "_reap_process", lambda process, graceful: False)
    await owner.reap()
    env.browser.new_browser_cdp_session.assert_not_awaited()
    stopped.assert_called_once_with(owner._scope_name)
    assert not owner.graceful_close


@pytest.mark.asyncio
async def test_browser_exit_grace_precedes_scope_stop(launch_env, monkeypatch) -> None:
    env = launch_env
    owner = cdp_launch.CdpLauncher(env.home)
    owner._process = env.process
    owner._browser = env.browser
    owner._browser_owned = True
    owner._scope_name = "gflow-cdp-ba39b5bb-1a37-4675-b43f-6290a3f935df.scope"
    events = []
    monkeypatch.setattr(
        cdp_launch, "_wait_process", lambda *args: events.append("natural_wait") or False
    )
    monkeypatch.setattr(cdp_launch, "_stop_owned_scope", lambda *args: events.append("scope_stop"))
    monkeypatch.setattr(
        cdp_launch, "_reap_process", lambda process, graceful: events.append("reap") or graceful
    )
    await owner.reap()
    assert events == ["natural_wait", "scope_stop", "reap"]
    assert not owner.graceful_close
