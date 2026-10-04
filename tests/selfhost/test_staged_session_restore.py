"""Owned private session restoration, including actual offline Chrome cookie lifecycle."""

import json
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

from gflow_cli.errors import ConfigurationError
from gflow_cli.selfhost.session_import import parse_cookie_table
from gflow_cli.selfhost.session_restore import prepare_staged_session_restore


@pytest.fixture
def staged(tmp_path, monkeypatch):
    from gflow_cli import auth

    home = tmp_path / "home"
    candidate = home / ".cookie-staging" / "candidate-fixture"
    default = candidate / "Default"
    default.mkdir(parents=True)
    candidate.chmod(0o700)
    prefs = default / "Preferences"
    prefs.write_text(json.dumps({"unrelated": {"keep": True}, "session": {"other": 7}}))
    monkeypatch.setattr(auth, "default_profile_root", lambda: home)
    table = parse_cookie_table("SID\tsynthetic-only\t.google.com\t/\tSession")
    metadata = candidate.stat()
    return candidate, prefs, table, (metadata.st_dev, metadata.st_ino)


def test_owned_preferences_merge_is_private_and_session_expiry_is_unchanged(staged):
    candidate, prefs, table, identity = staged
    before = table.playwright_cookies()
    prepare_staged_session_restore(candidate, table, owner_identity=identity)
    assert json.loads(prefs.read_text()) == {
        "unrelated": {"keep": True},
        "session": {"other": 7, "restore_on_startup": 1},
    }
    assert prefs.stat().st_mode & 0o777 == 0o600
    assert table.playwright_cookies() == before
    assert "expires" not in table.playwright_cookies()[0]
    assert not list(prefs.parent.glob(".session-restore-*"))


def test_persistent_only_import_does_not_modify_preferences(staged):
    candidate, prefs, _, identity = staged
    before = prefs.read_bytes()
    table = parse_cookie_table("SID\tsynthetic-only\t.google.com\t/\t" + str(time.time() + 3600))
    prepare_staged_session_restore(candidate, table, owner_identity=identity)
    assert prefs.read_bytes() == before


@pytest.mark.parametrize("bad", ["[]", "invalid", '{"session":[]}', '{"session":null}'])
def test_invalid_preferences_are_refused_without_replacement(staged, bad):
    candidate, prefs, table, identity = staged
    prefs.write_text(bad)
    with pytest.raises(ConfigurationError):
        prepare_staged_session_restore(candidate, table, owner_identity=identity)
    assert prefs.read_text() == bad


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversize"])
def test_preferences_require_bounded_regular_file(staged, tmp_path, kind):
    candidate, prefs, table, identity = staged
    prefs.unlink()
    if kind == "symlink":
        target = tmp_path / "original"
        target.write_text('{"original":true}')
        prefs.symlink_to(target)
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO fixture")
        os.mkfifo(prefs)
    else:
        prefs.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(ConfigurationError):
        prepare_staged_session_restore(candidate, table, owner_identity=identity)
    if kind == "symlink":
        assert target.read_text() == '{"original":true}'
    assert not list(prefs.parent.glob(".session-restore-*"))


@pytest.mark.parametrize("kind", ["original", "public", "identity", "default_symlink"])
def test_original_or_replaced_or_nonprivate_candidate_is_refused(staged, tmp_path, kind):
    candidate, prefs, table, identity = staged
    original = prefs.read_bytes()
    if kind == "original":
        moved = candidate.parent.parent / "profile_original"
        candidate.rename(moved)
        candidate = moved
        prefs = candidate / "Default" / "Preferences"
    elif kind == "public":
        candidate.chmod(0o755)
    elif kind == "identity":
        identity = (identity[0], identity[1] + 1)
    else:
        default = candidate / "Default"
        moved = tmp_path / "outside-default"
        default.rename(moved)
        default.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ConfigurationError):
        prepare_staged_session_restore(candidate, table, owner_identity=identity)
    assert prefs.read_bytes() == original


def test_failed_atomic_replace_preserves_original_and_cleans_temporary(staged, monkeypatch):
    from gflow_cli.selfhost import session_restore

    candidate, prefs, table, identity = staged
    before = prefs.read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic failure")

    monkeypatch.setattr(session_restore.os, "replace", fail_replace)
    with pytest.raises(ConfigurationError):
        prepare_staged_session_restore(candidate, table, owner_identity=identity)
    assert prefs.read_bytes() == before
    assert not list(prefs.parent.glob(".session-restore-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_real_importer_reader_session_loss_and_restore(staged, monkeypatch, restore):
    from gflow_cli.auth import strategies
    from gflow_cli.auth.cookies import _get_chrome_cookies_playwright
    from gflow_cli.selfhost.profile_import import _populate_candidate

    playwright = pytest.importorskip("playwright.async_api")
    candidate, prefs, _, identity = staged

    # Launch-time network isolation also covers restored pages before route installation.
    class OfflinePlaywright:
        async def __aenter__(self):
            self.manager = playwright.async_playwright()
            self.pw = await self.manager.__aenter__()

            async def launch(**kwargs):
                kwargs["headless"] = True
                kwargs["proxy"] = {"server": "http://127.0.0.1:9", "bypass": ""}
                kwargs.setdefault("args", []).append("--host-resolver-rules=MAP * ~NOTFOUND")
                context = await self.pw.chromium.launch_persistent_context(**kwargs)

                async def route(request):
                    if request.request.resource_type == "document":
                        await request.fulfill(
                            body="<body>offline synthetic fixture</body>", content_type="text/html"
                        )
                    else:
                        await request.abort()

                await context.route("**/*", route)
                return context

            return SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))

        async def __aexit__(self, *args):
            return await self.manager.__aexit__(*args)

    monkeypatch.setattr(strategies, "async_playwright", OfflinePlaywright)
    (candidate / ".gflow_browser_strategy").write_text("chrome")
    table = parse_cookie_table(
        "Name\tValue\tDomain\tPath\tExpires\tSecure\n"
        "SAPISID\tsynthetic-only\t.google.com\t/\tSession\ttrue\n"
        "OSID\tsynthetic-only\tflow.google.com\t/\tSession\ttrue\n"
        "__Secure-next-auth.session-token\tsynthetic-only\tlabs.google\t/fx\tSession\ttrue\n"
        "persistent-control\tsynthetic-only\t.google.com\t/\t" + str(time.time() + 3600) + "\tfalse"
    )
    await _populate_candidate(candidate, table)
    with sqlite3.connect(f"file:{candidate}/Default/Cookies?mode=ro", uri=True) as con:
        rows = con.execute("select expires_utc,is_persistent,has_expires from cookies").fetchall()
    assert len(rows) == 4 and sum(row == (0, 0, 0) for row in rows) == 3
    if restore:
        prepare_staged_session_restore(candidate, table, owner_identity=identity)
    snapshot = await _get_chrome_cookies_playwright(candidate)
    assert snapshot.google_session is restore
    assert len(snapshot.httpx_cookies) == int(restore)
    with sqlite3.connect(f"file:{candidate}/Default/Cookies?mode=ro", uri=True) as con:
        rows = con.execute("select expires_utc,is_persistent,has_expires from cookies").fetchall()
    assert sum(row == (0, 0, 0) for row in rows) == 3 * int(restore)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["no_session", "mismatch", "project"])
async def test_restore_keeps_strict_identity_project_gate_and_original(staged, monkeypatch, reason):
    from gflow_cli import auth
    from gflow_cli.auth import verification
    from gflow_cli.auth.verification import FlowSessionOutcome, FlowSessionStatus
    from gflow_cli.errors import AuthMissingError
    from gflow_cli.selfhost import profile_import

    fixture_candidate, _, table, _ = staged
    home = fixture_candidate.parent.parent
    monkeypatch.setattr(auth, "profile_dir", lambda name: home / f"profile_{name}")
    original = home / "profile_original"
    original.mkdir()
    (original / "Cookies").write_text("synthetic-original")
    expected = "expected@example.test"
    project = "00000000-0000-4000-8000-000000000099"
    calls = []
    verified_restore = []

    async def populate(candidate, table):
        default = candidate / "Default"
        default.mkdir()
        (default / "Preferences").write_text("{}")
        (candidate / "Cookies").write_text("synthetic-candidate")

    async def verify(candidate, **kwargs):
        assert (
            json.loads((candidate / "Default" / "Preferences").read_text())["session"][
                "restore_on_startup"
            ]
            == 1
        )
        verified_restore.append(1)
        if reason == "no_session":
            return FlowSessionStatus(FlowSessionOutcome.NO_SESSION, None, "synthetic")
        email = "other@example.test" if reason == "mismatch" else expected
        return FlowSessionStatus(FlowSessionOutcome.AUTHENTICATED, email, "synthetic")

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def list_native_media(self, selected):
            calls.append(selected)
            raise AuthMissingError(detail="Synthetic selected project unavailable")

    monkeypatch.setattr(profile_import, "_populate_candidate", populate)
    monkeypatch.setattr(verification, "verify_flow_profile", verify)
    monkeypatch.setattr("gflow_cli.api.client.FlowApiClient", Client)
    with pytest.raises(AuthMissingError):
        await profile_import.import_cookie_profile(
            table, "new", expected_email=expected, project_id=project
        )
    assert (original / "Cookies").read_text() == "synthetic-original"
    assert not (home / "profile_new").exists()
    assert list((home / ".cookie-staging").iterdir()) == [fixture_candidate]
    assert verified_restore == [1]
    assert calls == ([project] if reason == "project" else [])


def test_windows_private_candidate_uses_owned_hardening_marker(staged, monkeypatch, tmp_path):
    from gflow_cli.selfhost import session_restore
    from gflow_cli.winsec import ACL_MARKER

    candidate, _, _, _ = staged
    monkeypatch.setattr(session_restore, "os", SimpleNamespace(name="nt"))
    assert session_restore._private_candidate(candidate, 0o777) is False
    marker = candidate / ACL_MARKER
    marker.write_bytes(b"")
    assert session_restore._private_candidate(candidate, 0o777) is True
    marker.write_bytes(b"not-a-hardening-marker")
    assert session_restore._private_candidate(candidate, 0o777) is False
    marker.unlink()
    target = tmp_path / "outside-marker"
    target.write_bytes(b"")
    marker.symlink_to(target)
    assert session_restore._private_candidate(candidate, 0o777) is False
