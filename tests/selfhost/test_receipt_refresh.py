"""Cookie refresh carries only validated confirmed-delete metadata, never secrets."""

import hashlib
import json

import pytest

from gflow_cli.api.native_delete_receipts import DeleteReceipts
from gflow_cli.selfhost.receipt_refresh import carry_delete_receipts

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
N = "33333333-3333-4333-8333-333333333333"
EMAIL = "fixture@example.test"
OWNER = hashlib.sha256(EMAIL.encode()).hexdigest()


def profiles(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(mode=0o700)
    new.mkdir(mode=0o700)
    return old, new


def test_carries_exact_owned_receipts_and_preserves_original(tmp_path):
    old, new = profiles(tmp_path)
    receipts = DeleteReceipts(old, OWNER, P)
    receipts.record(M, "image")
    before = (receipts.root / (M + ".json")).read_bytes()
    (old / "Cookies").write_text("raw-cookie-secret")
    assert carry_delete_receipts(old, new, EMAIL) == 1
    assert DeleteReceipts(new, OWNER, P).kind(M) == "image"
    assert (receipts.root / (M + ".json")).read_bytes() == before
    assert not (new / "Cookies").exists()


def test_ignores_other_google_account_receipts(tmp_path):
    old, new = profiles(tmp_path)
    foreign = hashlib.sha256(b"other@example.test").hexdigest()
    DeleteReceipts(old, foreign, P).record(M, "image")
    assert carry_delete_receipts(old, new, EMAIL) == 0
    assert not (new / ".gflow_delete_receipts").exists()


def test_corrupt_or_conflicting_receipts_refuse_without_touching_old(tmp_path):
    old, new = profiles(tmp_path)
    receipts = DeleteReceipts(old, OWNER, P)
    receipts.record(M, "image")
    DeleteReceipts(new, OWNER, P).record(M, "video")
    with pytest.raises(ValueError, match="receipt"):
        carry_delete_receipts(old, new, EMAIL)
    assert receipts.kind(M) == "image"
    assert DeleteReceipts(new, OWNER, P).kind(M) == "video"


def test_source_symlink_and_world_readable_receipt_refuse(tmp_path):
    old, new = profiles(tmp_path)
    receipts = DeleteReceipts(old, OWNER, P)
    receipts.record(M, "image")
    (receipts.root / (M + ".json")).chmod(0o644)
    with pytest.raises(ValueError):
        carry_delete_receipts(old, new, EMAIL)
    (receipts.root / (M + ".json")).chmod(0o600)
    (receipts.root / (M + ".json")).unlink()
    outside = tmp_path / "foreign.json"
    outside.write_text("private")
    (receipts.root / (M + ".json")).symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        carry_delete_receipts(old, new, EMAIL)


def test_metadata_owner_and_media_must_match_exact_path(tmp_path):
    old, new = profiles(tmp_path)
    receipts = DeleteReceipts(old, OWNER, P)
    receipts.record(M, "image")
    target = receipts.root / (M + ".json")
    row = json.loads(target.read_text())
    row["media"] = N
    target.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        carry_delete_receipts(old, new, EMAIL)


def test_total_file_bound_refuses_before_any_copy(tmp_path, monkeypatch):
    old, new = profiles(tmp_path)
    source = DeleteReceipts(old, OWNER, P)
    source.record(M, "image")
    source.record(N, "video")
    monkeypatch.setattr("gflow_cli.selfhost.receipt_refresh.MAX_RECEIPT_FILES", 1)
    with pytest.raises(ValueError, match="bound"):
        carry_delete_receipts(old, new, EMAIL)
    assert not (new / ".gflow_delete_receipts").exists()
