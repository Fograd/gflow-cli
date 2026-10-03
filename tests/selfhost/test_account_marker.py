"""Private marker reads reject unbounded files and identity races."""

import os

import pytest

from gflow_cli.selfhost.account_marker import read_verified_account


@pytest.mark.parametrize("value", ["fixture@example.test", "fixture@example.test\n"])
def test_valid_marker(tmp_path, value):
    (tmp_path / ".gflow_account").write_text(value)
    assert read_verified_account(tmp_path) == "fixture@example.test"


@pytest.mark.parametrize("value", ["x" * 1025, "not-email", "a@b\nsecret", "\udcff"])
def test_invalid_marker(tmp_path, value):
    (tmp_path / ".gflow_account").write_bytes(value.encode("utf8", errors="surrogateescape"))
    assert read_verified_account(tmp_path) is None


def test_symlink_marker_and_profile_refused(tmp_path):
    target = tmp_path / "private"
    target.mkdir()
    (target / ".gflow_account").write_text("fixture@example.test")
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    assert read_verified_account(linked) is None
    (tmp_path / ".gflow_account").symlink_to(target / ".gflow_account")
    assert read_verified_account(tmp_path) is None


def test_replacement_during_read_refused(tmp_path, monkeypatch):
    marker = tmp_path / ".gflow_account"
    marker.write_text("fixture@example.test")
    real_read = os.read

    def replace_during_read(fd, count):
        raw = real_read(fd, count)
        marker.unlink()
        marker.write_text("replacement@example.test")
        return raw

    monkeypatch.setattr(os, "read", replace_during_read)
    assert read_verified_account(tmp_path) is None


def test_portable_without_nofollow(tmp_path, monkeypatch):
    (tmp_path / ".gflow_account").write_text("fixture@example.test")
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    assert read_verified_account(tmp_path) == "fixture@example.test"


def test_same_inode_mutation_during_read_refused(tmp_path, monkeypatch):
    marker = tmp_path / ".gflow_account"
    marker.write_text("fixture@example.test")
    real_read = os.read
    changed = False

    def mutate(fd, count):
        nonlocal changed
        raw = real_read(fd, count)
        if not changed:
            changed = True
            marker.write_text("other@example.test")
        return raw

    monkeypatch.setattr(os, "read", mutate)
    assert read_verified_account(tmp_path) is None


def test_short_reads_are_completed(tmp_path, monkeypatch):
    (tmp_path / ".gflow_account").write_text("fixture@example.test")
    real_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, count: real_read(fd, min(count, 3)))
    assert read_verified_account(tmp_path) == "fixture@example.test"
