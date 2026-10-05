"""Experimental owned system-Chrome launch; the regular launcher remains unchanged.

The caller owns the profile lease. This module never attaches to another browser,
creates an incognito context, imports cookies, or navigates a page. Its process
owner must be retained before awaiting ``launch`` and reaped before lease release.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import structlog

from gflow_cli.config import BrowserEngine, get_settings
from gflow_cli.errors import AuthExpiredError, ConfigurationError, ProfileAccessError, SecurityError

log = structlog.get_logger(__name__)

_STARTUP_TIMEOUT_S = 30.0
_CONNECT_TIMEOUT_S = 15.0
_BROWSER_CLOSE_TIMEOUT_S = 20.0
_EXIT_GRACE_S = 5.0
_STOP_TIMEOUT_S = 5.0
_MAX_PORT_FILE_BYTES = 256
_ALLOWED_KWARGS = frozenset(
    {
        "user_data_dir",
        "headless",
        "channel",
        "args",
        "ignore_default_args",
        "viewport",
        "locale",
        "extra_http_headers",
    }
)
_FORBIDDEN_ARGS = frozenset(
    {
        "--user-data-dir",
        "--remote-debugging-port",
        "--remote-debugging-address",
        "--remote-debugging-pipe",
        "--remote-allow-origins",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-seccomp-filter-sandbox",
        "--disable-web-security",
        "--allow-file-access-from-files",
        "--headless",
        "--enable-automation",
        "--lang",
        "--proxy-server",
        "--proxy-pac-url",
        "--ignore-certificate-errors",
    }
)
_ALLOWED_CHROME_FLAGS = frozenset(
    {
        "--password-store",
        "--disable-blink-features",
        "--disable-dev-shm-usage",
        "--restore-last-session",
        "--window-position",
        "--window-size",
    }
)


def _configuration(detail: str) -> ConfigurationError:
    return ConfigurationError(
        detail=f"Owned CDP startup: {detail}",
        remediation_hint="Disable GFLOW_CLI_CDP_LAUNCH to use the regular browser launcher.",
    )


def _system_chrome() -> str:
    """Use installed stable Chrome's standard location, never PATH or overrides."""
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Google/Chrome/Application/chrome.exe"
        ]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        candidates = [Path("/opt/google/chrome/chrome")]
    for candidate in candidates:
        if candidate.is_file() and (sys.platform == "win32" or os.access(candidate, os.X_OK)):
            return str(candidate)
    raise _configuration("installed stable Google Chrome is unavailable at its standard location")


def _validate_profile(home: Path, value: Any) -> Path:
    if not isinstance(value, (str, Path)):
        raise SecurityError("CDP requires an existing original profile directory.")
    try:
        profile = Path(value).absolute()
        root = home.resolve(strict=True)
        resolved = profile.resolve(strict=True)
        if resolved == root or not resolved.is_relative_to(root) or resolved != profile:
            raise SecurityError("CDP profile must be canonical and remain inside GFLOW_CLI_HOME.")
        for directory in (resolved, *resolved.parents):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise SecurityError("CDP profile ancestry is not a directory.")
            if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o022):
                raise SecurityError(
                    "CDP profile ancestry must be owned and not group/world writable."
                )
            if directory == root:
                break
        return resolved
    except OSError as exc:
        raise SecurityError(
            "CDP requires an existing, accessible original profile directory."
        ) from exc


def _validated_options(
    kwargs: dict[str, Any],
) -> tuple[list[str], dict[str, int], str, dict[str, str]]:
    unknown = set(kwargs) - _ALLOWED_KWARGS
    if unknown:
        raise _configuration("unsupported context options: " + ", ".join(sorted(unknown)))
    if get_settings().browser_engine != BrowserEngine.PATCHRIGHT:
        raise _configuration("the experimental launcher requires the Patchright engine")
    if get_settings().flow_host == "labs.google":
        raise _configuration("only migrated flow.google.com profiles are supported")
    if kwargs.get("headless") is not False or kwargs.get("channel") != "chrome":
        raise _configuration("only headed, installed system-Chrome profiles are supported")
    viewport_input = kwargs.get("viewport")
    if not isinstance(viewport_input, dict):
        raise _configuration("a width/height viewport is required")
    viewport = cast("dict[str, Any]", viewport_input)
    if set(viewport) != {"width", "height"}:
        raise _configuration("a width/height viewport is required")
    if any(type(value) is not int or not 1 <= value <= 16384 for value in viewport.values()):
        raise _configuration("viewport dimensions must be positive bounded integers")
    locale = kwargs.get("locale")
    if not isinstance(locale, str) or not re.fullmatch(
        r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", locale
    ):
        raise _configuration("a valid locale is required")
    headers_input = kwargs.get("extra_http_headers", {})
    if not isinstance(headers_input, dict):
        raise _configuration("HTTP headers must be valid string pairs")
    headers = cast("dict[Any, Any]", headers_input)
    if any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
        or any(char in value for char in "\r\n\x00")
        for key, value in headers.items()
    ):
        raise _configuration("HTTP headers must be valid string pairs")
    ignored_input = kwargs.get("ignore_default_args", [])
    if not isinstance(ignored_input, list):
        raise _configuration("unsupported ignore_default_args")
    ignored = cast("list[Any]", ignored_input)
    if any(
        not isinstance(item, str) or item not in {"--enable-automation", "--no-sandbox"}
        for item in ignored
    ):
        raise _configuration("unsupported ignore_default_args")
    args_input = kwargs.get("args", [])
    if not isinstance(args_input, list):
        raise _configuration("Chrome arguments must be a list of strings")
    untyped_args = cast("list[Any]", args_input)
    if any(not isinstance(item, str) for item in untyped_args):
        raise _configuration("Chrome arguments must be a list of strings")
    args = cast("list[str]", untyped_args)
    for arg in args:
        name = arg.split("=", 1)[0]
        if (
            not arg.startswith("--")
            or any(char in arg for char in "\r\n\x00")
            or name in _FORBIDDEN_ARGS
            or name not in _ALLOWED_CHROME_FLAGS
        ):
            raise _configuration("conflicting or unsafe Chrome arguments are unsupported")
        if name == "--password-store" and arg != "--password-store=basic":
            raise _configuration("the original profile requires password-store=basic")
        if name == "--disable-blink-features" and arg != (
            "--disable-blink-features=AutomationControlled"
        ):
            raise _configuration("only the established AutomationControlled flag is supported")
        if name in {"--disable-dev-shm-usage", "--restore-last-session"} and arg != name:
            raise _configuration("unexpected value for a preserved Chrome flag")
        if name == "--window-position" and not re.fullmatch(r"--window-position=-?\d+,-?\d+", arg):
            raise _configuration("window position must be an integer coordinate pair")
        if name == "--window-size" and not re.fullmatch(r"--window-size=\d+,\d+", arg):
            raise _configuration("window size must be an integer dimension pair")
    if "--password-store=basic" not in args:
        raise _configuration("password-store=basic must be preserved")
    copied_headers = headers.copy()
    # CDP has no Playwright context locale setting to supply this header.
    # Preserve an explicit request policy, otherwise match locale's header.
    if not any(key.casefold() == "accept-language" for key in copied_headers):
        copied_headers["Accept-Language"] = locale
    return args.copy(), cast("dict[str, int]", viewport.copy()), locale, copied_headers


def _file_snapshot(path: Path) -> tuple[int, ...] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_PORT_FILE_BYTES:
        raise SecurityError("CDP debugger rendezvous must be a small regular file.")
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o022):
        raise SecurityError("CDP debugger rendezvous has unsafe ownership or permissions.")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_endpoint(path: Path, before: tuple[int, ...] | None) -> str | None:
    snapshot = _file_snapshot(path)
    if snapshot is None or snapshot == before:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        opened = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if opened != snapshot or not stat.S_ISREG(info.st_mode):
            raise SecurityError("CDP debugger rendezvous changed while opening.")
        raw = os.read(fd, _MAX_PORT_FILE_BYTES + 1)
        if _file_snapshot(path) != snapshot:
            return None
        if os.name == "posix":
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    try:
        lines = raw.decode("ascii").splitlines()
        if len(lines) < 2:
            return None
        if len(lines) != 2 or not lines[0].isdigit():
            raise ValueError
        port = int(lines[0])
        if not 1 <= port <= 65535 or not lines[1].startswith("/devtools/browser/"):
            raise ValueError
        identifier = lines[1].removeprefix("/devtools/browser/")
        if str(UUID(identifier)) != identifier:
            raise ValueError
    except (ValueError, UnicodeDecodeError) as exc:
        raise _configuration("Chrome published an invalid debugger rendezvous") from exc
    return f"ws://127.0.0.1:{port}{lines[1]}"


async def _wait_endpoint(
    path: Path,
    process: subprocess.Popen[bytes],
    before: tuple[int, ...] | None,
) -> str:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise _configuration("the owned Chrome process exited before debugger readiness")
        try:
            endpoint = _read_endpoint(path, before)
        except FileNotFoundError:
            endpoint = None
        if endpoint is not None:
            return endpoint
        await asyncio.sleep(0.05)
    raise _configuration("the owned Chrome process did not publish fresh debugger readiness")


def _spawn_process(cmd: list[str]) -> subprocess.Popen[bytes]:
    # Synchronous handoff assigns ownership before the first cancellable await.
    return subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def _linux_group_live_members(pid: int) -> list[int]:
    # LXC PID1 can retain adopted zombies after Chrome has exited. Zombies
    # have no open files or running code and cannot hold the profile lock.
    # Treat unreadable status as unknown/live; only positively exited members
    # are discounted, without signalling or reaping unrelated processes.
    members: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rpartition(") ")[2].split()
            if len(fields) < 3:
                raise _configuration("cannot establish owned Chrome child state")
            if int(fields[2]) == pid and fields[0] not in {"Z", "X"}:
                members.append(int(entry.name))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise _configuration("cannot establish owned Chrome child state") from exc
    return members


def _group_running(pid: int) -> bool:
    if os.name != "posix":
        return False
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if sys.platform.startswith("linux"):
        return bool(_linux_group_live_members(pid))
    return True


def _signal_process(process: subprocess.Popen[bytes], *, force: bool) -> None:
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    elif process.poll() is None:
        cmd = ["taskkill", "/T", "/PID", str(process.pid)]
        if force:
            cmd.append("/F")
        subprocess.run(cmd, capture_output=True, check=False, timeout=_STOP_TIMEOUT_S)


def _wait_process(process: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    while _group_running(process.pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _reap_process(process: subprocess.Popen[bytes], graceful: bool) -> bool:
    if graceful and _wait_process(process, _EXIT_GRACE_S):
        return True
    if process.poll() is not None and not _group_running(process.pid):
        process.wait(timeout=0)
        return graceful
    _signal_process(process, force=False)
    if not _wait_process(process, _STOP_TIMEOUT_S):
        _signal_process(process, force=True)
        if not _wait_process(process, _STOP_TIMEOUT_S):
            raise _configuration("owned Chrome did not exit; keep the profile lease held")
    return False


def _stop_owned_scope(unit: str, browser_pid: int | None = None) -> None:
    """Stop only this invocation's transient scope, including detached children."""
    if (
        re.fullmatch(r"gflow-cdp-[0-9a-f-]{36}\.scope", unit) is None
        and unit != f"app-com.google.Chrome-{browser_pid}.scope"
    ):
        raise SecurityError("Refusing to stop an unowned Chrome scope name.")
    group_result = subprocess.run(
        ["/usr/bin/systemctl", "--user", "show", unit, "--property=ControlGroup", "--value"],
        capture_output=True,
        timeout=5,
        check=False,
    )
    if group_result.returncode != 0:
        raise _configuration("cannot establish owned Chrome scope state")
    group = group_result.stdout.decode().strip()
    if group and (
        not group.startswith("/") or ".." in group.split("/") or not group.endswith("/" + unit)
    ):
        raise SecurityError("Chrome scope control-group ownership differs.")
    subprocess.run(
        ["/usr/bin/systemctl", "--user", "stop", unit],
        capture_output=True,
        timeout=10,
        check=False,
    )
    state = subprocess.run(
        ["/usr/bin/systemctl", "--user", "show", unit, "--property=ActiveState", "--value"],
        capture_output=True,
        timeout=5,
        check=False,
    )
    if state.returncode == 0 and state.stdout.strip() == b"inactive":
        if group:
            events = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.events"
            try:
                fields = dict(line.split() for line in events.read_text().splitlines())
                if fields.get("populated") != "0":
                    raise _configuration("owned Chrome scope still contains processes")
            except FileNotFoundError:
                pass  # Removed kernel control group cannot contain processes.
        return
    raise _configuration("owned Chrome scope did not stop; keep the profile lease held")


class _CdpContext:
    """Context API delegation, with owned shutdown and options on future pages."""

    def __init__(self, context: Any, owner: CdpLauncher) -> None:
        self._context = context
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)

    @property
    def graceful_close(self) -> bool:
        return self._owner.graceful_close

    async def new_page(self) -> Any:
        page = await self._context.new_page()
        await self._owner.configure_page(self._context, page)
        return page

    async def close(self) -> None:
        await self._owner.reap()


class CdpLauncher:
    """Owner of exactly one Chrome process tree; caller owns the profile lease."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self._process: subprocess.Popen[bytes] | None = None
        self._browser: Any = None
        self._reap_task: asyncio.Task[None] | None = None
        self._reaped = False
        self._viewport: dict[str, int] = {}
        self._locale = ""
        self._port: int | None = None
        self._graceful_close = False
        self._page_sessions: list[Any] = []
        self._scope_name: str | None = None
        self._browser_pid: int | None = None
        self._app_scope_name: str | None = None
        self._browser_owned = False

    @property
    def process_pid(self) -> int | None:
        return self._browser_pid or (self._process.pid if self._process is not None else None)

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def process_running(self) -> bool:
        if self._process is None or self._reaped:
            return False
        if self._scope_name is not None:
            return True  # Only successful scope cleanup can establish detached-child exit.
        return self._process.poll() is None or _group_running(self._process.pid)

    @property
    def graceful_close(self) -> bool:
        return self._graceful_close

    async def configure_page(self, context: Any, page: Any) -> None:
        """Apply context-equivalent options before a managed page is navigated."""
        await page.set_viewport_size(self._viewport)
        session = await context.new_cdp_session(page)
        self._page_sessions.append(session)
        await session.send("Emulation.setLocaleOverride", {"locale": self._locale})

    async def _check_original_session(self, context: Any) -> None:
        try:
            cookies = await context.cookies()
        except Exception as exc:
            raise AuthExpiredError(
                detail="The owned Chrome context could not verify its original Flow session.",
            ) from exc
        now = time.time()
        # Migrated Flow authenticates with the original Google session rather
        # than the labs next-auth cookie. Cookies are a preflight hint only;
        # verify_native_identity binds the actual signed-in principal after goto.
        native_allowed = get_settings().flow_host != "labs.google"
        for cookie in cookies:
            expires = cookie.get("expires")
            if (
                (
                    cookie.get("name") == "__Secure-next-auth.session-token"
                    or (
                        native_allowed
                        and cookie.get("name")
                        in {"SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID"}
                        and cookie.get("domain", "").lstrip(".") == "google.com"
                    )
                )
                and isinstance(cookie.get("value"), str)
                and bool(cookie["value"])
                and cookie.get("domain", "").lstrip(".")
                in {
                    "flow.google.com",
                    "labs.google",
                    "google.com",
                }
                and cookie.get("secure") is True
                and isinstance(expires, (int, float))
                and not isinstance(expires, bool)
                and math.isfinite(expires)
                and (expires == -1 or expires > now)
            ):
                return
        raise AuthExpiredError(
            detail="Original Flow session absent or expired; CDP startup does not import cookies.",
        )

    async def verify_native_identity(self, page: Any, profile: Path) -> None:
        """Bind migrated Flow's actual principal to the original profile marker."""
        origin = urlsplit(str(page.url))
        if origin.scheme != "https" or origin.netloc != "flow.google.com":
            raise AuthExpiredError(detail="Owned Chrome did not reach authenticated native Flow.")
        from gflow_cli.auth.native_identity import read_native_identity
        from gflow_cli.profile_store import read_account_file

        expected = read_account_file(profile)
        if not expected:
            raise AuthExpiredError(detail="Owned CDP requires an original recorded account.")
        try:
            await page.wait_for_function(
                "() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=30000
            )
            actual = await read_native_identity(page)
        except Exception as exc:
            raise AuthExpiredError(
                detail="Owned Chrome could not verify its native Flow account."
            ) from exc
        if actual.casefold() != expected.casefold():
            raise SecurityError("Owned Chrome account differs from the original profile account.")

    async def launch(self, pw: Any, kwargs: dict[str, Any]) -> Any:
        if self._process is not None or self._reap_task is not None:
            raise _configuration("a launcher owner cannot be reused")
        args, self._viewport, self._locale, headers = _validated_options(kwargs)
        profile = _validate_profile(self.home, kwargs.get("user_data_dir"))
        chrome = _system_chrome()
        port_file = profile / "DevToolsActivePort"
        before = _file_snapshot(port_file)
        cmd = [
            chrome,
            f"--user-data-dir={profile}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            f"--lang={self._locale}",
            *args,
        ]
        if sys.platform.startswith("linux"):
            if (
                not Path("/usr/bin/systemd-run").is_file()
                or not Path("/usr/bin/systemctl").is_file()
            ):
                raise _configuration("Linux owned launch requires an active user systemd manager")
            self._scope_name = f"gflow-cdp-{uuid4()}.scope"
            cmd = [
                "/usr/bin/systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--unit=" + self._scope_name,
                "--property=KillMode=control-group",
                "--property=TimeoutStopSec=5s",
                "--",
                *cmd,
            ]
        phase = "spawn"
        try:
            self._process = _spawn_process(cmd)
            phase = "readiness"
            endpoint = await _wait_endpoint(port_file, self._process, before)
            self._port = int(endpoint.split(":", 2)[2].split("/", 1)[0])
            phase = "attach"
            self._browser = await asyncio.wait_for(
                pw.chromium.connect_over_cdp(endpoint),
                timeout=_CONNECT_TIMEOUT_S,
            )
            if self._scope_name is None:
                self._browser_owned = True
            if len(self._browser.contexts) != 1:
                raise _configuration(
                    "Chrome did not expose exactly one original persistent context"
                )
            context = self._browser.contexts[0]
            if self._scope_name is not None:
                phase = "process_ownership"
                session = await self._browser.new_browser_cdp_session()
                info = await session.send("SystemInfo.getProcessInfo")
                candidates = [
                    entry.get("id")
                    for entry in info.get("processInfo", [])
                    if entry.get("type") == "browser"
                ]
                if len(candidates) != 1 or type(candidates[0]) is not int:
                    raise _configuration("cannot identify the owned Chrome process")
                browser_pid = candidates[0]
                process_root = Path("/proc") / str(browser_pid)
                if (process_root / "exe").readlink() != Path(chrome):
                    raise SecurityError("CDP browser executable differs from this invocation.")
                groups = (process_root / "cgroup").read_text().splitlines()
                process_fields = (process_root / "stat").read_text().rpartition(") ")[2].split()
                if int(process_fields[2]) != self._process.pid:
                    raise SecurityError("CDP browser differs from the owned process group.")
                app_scope = f"app-com.google.Chrome-{browser_pid}.scope"
                actual_units = [line.rpartition("/")[2] for line in groups]
                if self._scope_name not in actual_units:
                    # Chrome registers its own desktop scope and moves itself
                    # out of the launch scope. Admit only this freshly owned
                    # PID's exact scope after the independent process-group gate.
                    if app_scope not in actual_units:
                        raise SecurityError("CDP browser is outside its owned transient scopes.")
                    self._app_scope_name = app_scope
                self._browser_pid = browser_pid
                await session.detach()
            self._browser_owned = True
            phase = "original_session"
            await self._check_original_session(context)
            phase = "headers"
            await context.set_extra_http_headers(headers)
            phase = "page_options"
            for page in context.pages:
                await self.configure_page(context, page)
            log.info("client.cdp_launch", chrome=chrome, port=self._port, owned=True)
            return _CdpContext(context, self)
        except BaseException as exc:
            log.warning("client.cdp_launch_failed", phase=phase, error_class=type(exc).__name__)
            await self.reap()
            if isinstance(exc, (ConfigurationError, SecurityError, AuthExpiredError)):
                raise
            if isinstance(exc, PermissionError):
                raise ProfileAccessError(
                    detail="Owned Chrome could not start with access to the original profile.",
                ) from None
            if not isinstance(exc, Exception):
                raise
            raise _configuration(f"failed during {phase} ({type(exc).__name__})") from None

    async def _cleanup(self) -> None:
        if self._process is None:
            self._reaped = True
            return
        close_ok = False
        if self._browser is not None and self._browser_owned:

            async def close_browser() -> None:
                session = await self._browser.new_browser_cdp_session()
                await session.send("Browser.close")

            try:
                await asyncio.wait_for(
                    close_browser(),
                    timeout=_BROWSER_CLOSE_TIMEOUT_S,
                )
                close_ok = True
            except Exception:
                log.warning("client.cdp_browser_close_failed")
        # Browser.close acknowledgement is not proof of profile flush/exit.
        # Give the owned root process its natural-exit grace before any scope
        # escalation. Detached children remain contained by the two owned scopes.
        natural_exit = False
        if close_ok:
            natural_exit = await asyncio.to_thread(_wait_process, self._process, _EXIT_GRACE_S)
        if self._app_scope_name is not None:
            await asyncio.to_thread(_stop_owned_scope, self._app_scope_name, self._browser_pid)
        if self._scope_name is not None:
            await asyncio.to_thread(_stop_owned_scope, self._scope_name)
        cleanup_graceful = await asyncio.to_thread(_reap_process, self._process, natural_exit)
        self._graceful_close = bool(close_ok and natural_exit and cleanup_graceful)
        self._reaped = True
        self._page_sessions = []
        log.info("client.cdp_reaped", graceful=self._graceful_close)

    async def reap(self) -> None:
        """Finish owned cleanup before propagating even repeated caller cancellation."""
        if self._reap_task is None or (self._reap_task.done() and not self._reaped):
            self._reap_task = asyncio.create_task(self._cleanup())
        cancelled: asyncio.CancelledError | None = None
        while not self._reap_task.done():
            try:
                await asyncio.shield(self._reap_task)
            except asyncio.CancelledError as exc:
                cancelled = exc
        self._reap_task.result()
        if cancelled is not None:
            raise cancelled
