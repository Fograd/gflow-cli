"""Staged-profile invariants, exercised without browser/network."""

from __future__ import annotations

import asyncio

import pytest

from gflow_cli import auth
from gflow_cli.errors import AuthMissingError, ConfigurationError, ProfileLockedError
from gflow_cli.profile_lease import ProfileLease
from gflow_cli.selfhost import profile_import as module
from gflow_cli.selfhost.session_import import parse_cookie_table

P = "11111111-1111-4111-8111-111111111111"
E = "operator@example.test"


@pytest.fixture
def table():
    return parse_cookie_table("SID\tprivate-test-value\t.google.com\t/\tSession")


@pytest.mark.asyncio
async def test_staged_success_activates_only_verified_private_candidate(monkeypatch, table):
    calls = []

    async def populate(path, data):
        assert not auth.profile_dir("new").exists()
        assert path.parent.name == ".cookie-staging"
        assert path.stat().st_mode & 0o077 == 0
        (path / "Cookies").write_text("private-test-value")
        calls.append("populate")

    async def verify(path, expected, project):
        assert (path / "Cookies").exists()
        assert not auth.profile_dir("new").exists()
        calls.append("verify")
        return E, P

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    result = await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    assert calls == ["populate", "verify"]
    assert result.profile == "new"
    assert result.email == E
    assert result.project_id == P
    assert "private-test-value" not in repr(result)
    target = auth.profile_dir("new")
    assert (target / ".gflow_account").read_text() == E
    assert (target / ".gflow_account").stat().st_mode & 0o077 == 0
    assert not list((target.parent / ".cookie-staging").iterdir())
    with ProfileLease(target):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["populate", "verify", "cancel"])
async def test_rejected_or_cancelled_candidate_is_removed_and_lease_released(
    monkeypatch, table, reason
):
    async def populate(path, data):
        (path / "Cookies").write_text("private-test-value")
        if reason == "populate":
            raise RuntimeError("private-test-value")
        if reason == "cancel":
            raise asyncio.CancelledError()

    async def verify(*args):
        raise RuntimeError("private-test-value")

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    expected = asyncio.CancelledError if reason == "cancel" else AuthMissingError
    with pytest.raises(expected) as error:
        await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    assert "private-test-value" not in str(error.value)
    target = auth.profile_dir("new")
    assert not target.exists()
    assert not list((target.parent / ".cookie-staging").iterdir())
    with ProfileLease(target):
        pass


@pytest.mark.asyncio
async def test_existing_profile_is_not_touched(monkeypatch, table):
    target = auth.profile_dir("original")
    target.mkdir(parents=True)
    sentinel = target / "Cookies"
    sentinel.write_text("original-private-value")

    async def forbidden(*args):
        pytest.fail("Existing profiles must be refused before browser")

    monkeypatch.setattr(module, "_populate_candidate", forbidden)
    with pytest.raises(ConfigurationError):
        await module.import_cookie_profile(table, "original", expected_email=E, project_id=P)
    assert sentinel.read_text() == "original-private-value"


@pytest.mark.asyncio
async def test_busy_target_refused_before_browser(monkeypatch, table):
    async def forbidden(*args):
        pytest.fail("Contended target must never start browser")

    monkeypatch.setattr(module, "_populate_candidate", forbidden)
    with ProfileLease(auth.profile_dir("new")):
        with pytest.raises(ProfileLockedError):
            await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)


@pytest.mark.asyncio
async def test_symlink_staging_is_refused_before_browser(monkeypatch, table, tmp_path):
    home = auth.default_profile_root()
    home.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / ".cookie-staging").symlink_to(outside, target_is_directory=True)

    async def forbidden(*args):
        pytest.fail("Symlink staging must never start browser")

    monkeypatch.setattr(module, "_populate_candidate", forbidden)
    with pytest.raises(ConfigurationError):
        await module.import_cookie_profile(table, "new")
    assert not list(outside.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["../escape", "", "a/b"])
async def test_invalid_names_refused_before_browser(monkeypatch, table, profile):
    async def forbidden(*args):
        pytest.fail("Invalid input must never start browser")

    monkeypatch.setattr(module, "_populate_candidate", forbidden)
    with pytest.raises(ConfigurationError):
        await module.import_cookie_profile(table, profile)


@pytest.mark.asyncio
async def test_cleanup_proves_imported_directory_identity(monkeypatch, table):
    async def populate(path, data):
        (path / "Cookies").write_text("private-test-value")

    async def verify(*args):
        return E, P

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    imported = await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    target = auth.profile_dir("new")
    parked = target.with_name("parked")
    target.rename(parked)
    target.mkdir()
    sentinel = target / "Cookies"
    sentinel.write_text("replacement-private-value")
    assert await module.discard_imported_profile(imported) is False
    assert sentinel.read_text() == "replacement-private-value"


@pytest.mark.asyncio
async def test_cleanup_refuses_used_import_and_busy_import(monkeypatch, table):
    async def populate(path, data):
        (path / "Cookies").write_text("private-test-value")

    async def verify(*args):
        return E, P

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    imported = await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    target = auth.profile_dir("new")
    with ProfileLease(target):
        assert await module.discard_imported_profile(imported) is False
    (target / ".gflow_account").write_text("changed@example.test")
    assert await module.discard_imported_profile(imported) is False
    assert target.exists()


@pytest.mark.asyncio
async def test_cleanup_removes_only_owned_unchanged_import(monkeypatch, table):
    async def populate(path, data):
        (path / "Cookies").write_text("private-test-value")

    async def verify(*args):
        return E, P

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    imported = await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    assert await module.discard_imported_profile(imported) is True
    assert not auth.profile_dir("new").exists()
    assert await module.discard_imported_profile(imported) is False


@pytest.mark.asyncio
async def test_fingerprint_failure_leaves_no_activated_credentials(monkeypatch, table):
    async def populate(path, data):
        (path / "Cookies").write_text("private-test-value")

    async def verify(*args):
        return E, P

    def fail_fingerprint(path):
        raise OSError("private-test-value")

    monkeypatch.setattr(module, "_populate_candidate", populate)
    monkeypatch.setattr(module, "_verify_candidate", verify)
    monkeypatch.setattr(module, "_fingerprint", fail_fingerprint)
    with pytest.raises(AuthMissingError) as error:
        await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    assert "private-test-value" not in str(error.value)
    assert not auth.profile_dir("new").exists()
    assert not list((auth.default_profile_root() / ".cookie-staging").iterdir())


@pytest.mark.asyncio
async def test_candidate_acl_failure_is_safe_and_removes_staging(monkeypatch, table):
    from gflow_cli import winsec

    original = winsec.ensure_profile_hardened

    def failing_acl(path):
        if path.name.startswith("candidate-"):
            raise OSError("private-test-value")
        return original(path)

    monkeypatch.setattr(winsec, "ensure_profile_hardened", failing_acl)
    with pytest.raises(AuthMissingError) as error:
        await module.import_cookie_profile(table, "new", expected_email=E, project_id=P)
    assert "private-test-value" not in str(error.value)
    assert not auth.profile_dir("new").exists()
    assert not list((auth.default_profile_root() / ".cookie-staging").iterdir())
