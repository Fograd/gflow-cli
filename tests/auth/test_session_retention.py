"""Owned verified profile launch retention; isolated synthetic fixtures only."""

import pytest

from gflow_cli.auth.session_retention import session_retention_args


@pytest.fixture
def profile(tmp_path):
    path = tmp_path / "profile_synthetic"
    path.mkdir(mode=0o700)
    for name, value in [
        (".gflow_browser_strategy", "chrome"),
        (".gflow_account", "synthetic@example.test"),
    ]:
        marker = path / name
        marker.write_text(value)
        marker.chmod(0o600)
    return path


def test_verified_private_chrome_only(profile):
    assert session_retention_args(profile, "chrome") == ["--restore-last-session"]
    assert session_retention_args(profile, None) == []


@pytest.mark.parametrize(
    "problem",
    [
        "noaccount",
        "badaccount",
        "publicaccount",
        "symlinkaccount",
        "badengine",
        "publicprofile",
        "hugeengine",
    ],
)
def test_untrusted_marker_never_restores(profile, tmp_path, problem):
    marker = profile / ".gflow_account"
    if problem == "noaccount":
        marker.unlink()
    elif problem == "badaccount":
        marker.write_text("unknown")
    elif problem == "publicaccount":
        marker.chmod(0o644)
    elif problem == "symlinkaccount":
        target = tmp_path / "foreign"
        target.write_text("synthetic@example.test")
        marker.unlink()
        marker.symlink_to(target)
    elif problem == "badengine":
        (profile / ".gflow_browser_strategy").write_text("chromium")
    elif problem == "hugeengine":
        (profile / ".gflow_browser_strategy").write_text("x" * 1025)
    else:
        profile.chmod(0o755)
    assert session_retention_args(profile, "chrome") == []


def test_sdk_launch_uses_guarded_retention(profile, monkeypatch):
    from gflow_cli.api.client import FlowApiClient

    monkeypatch.setattr("gflow_cli.api.client.channel_for_profile", lambda _: "chrome")
    args = FlowApiClient(profile_dir=profile)._persistent_context_kwargs()["args"]
    assert args.count("--restore-last-session") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [True, False])
async def test_real_offline_chrome_session_cold_reopen(profile, monkeypatch, verified):
    import sqlite3

    from playwright.async_api import async_playwright

    from gflow_cli.api.client import FlowApiClient

    if not verified:
        (profile / ".gflow_account").unlink()
    monkeypatch.setattr("gflow_cli.api.client.channel_for_profile", lambda _: "chrome")
    kwargs = FlowApiClient(profile_dir=profile, headless=True)._persistent_context_kwargs()
    kwargs["proxy"] = {"server": "http://127.0.0.1:9"}
    kwargs["args"] += [
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost",
        "--disable-background-networking",
    ]
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(**kwargs)
        await ctx.route("**/*", lambda route: route.abort())
        await ctx.add_cookies(
            [
                {
                    "name": "synthetic-session",
                    "value": "synthetic-only",
                    "domain": "example.test",
                    "path": "/",
                    "secure": True,
                }
            ]
        )
        assert len(await ctx.cookies()) == 1
        await ctx.close()
        ctx = await pw.chromium.launch_persistent_context(**kwargs)
        try:
            await ctx.route("**/*", lambda route: route.abort())
            cookies = await ctx.cookies()
            assert [cookie["name"] for cookie in cookies] == (
                ["synthetic-session"] if verified else []
            )
            if cookies:
                assert cookies[0]["expires"] == -1
        finally:
            await ctx.close()
    with sqlite3.connect(f"file:{profile}/Default/Cookies?mode=ro", uri=True) as con:
        rows = con.execute("select expires_utc,is_persistent,has_expires from cookies").fetchall()
    assert rows == ([(0, 0, 0)] if verified else [])


def test_foreign_owner_and_profile_alias_never_restore(profile, tmp_path, monkeypatch):
    import os

    actual_uid = os.getuid()
    monkeypatch.setattr("gflow_cli.auth.session_retention.os.getuid", lambda: actual_uid + 1)
    assert session_retention_args(profile, "chrome") == []
    monkeypatch.undo()
    alias = tmp_path / "profile_alias"
    alias.symlink_to(profile, target_is_directory=True)
    assert session_retention_args(alias, "chrome") == []


def test_marker_replacement_during_bounded_read_refuses(profile, monkeypatch):
    from gflow_cli.auth import session_retention

    original = session_retention.os.read
    replaced = False

    def replacing(fd, size):
        nonlocal replaced
        value = original(fd, size)
        if not replaced:
            replaced = True
            marker = profile / ".gflow_browser_strategy"
            marker.unlink()
            marker.write_text("chrome")
            marker.chmod(0o600)
        return value

    monkeypatch.setattr(session_retention.os, "read", replacing)
    assert session_retention_args(profile, "chrome") == []
