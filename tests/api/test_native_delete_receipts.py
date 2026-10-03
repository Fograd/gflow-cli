from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.native_delete_receipts import DeleteReceipts, verified_delete_receipts

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
N = "33333333-3333-4333-8333-333333333333"


def test_receipts_are_private_and_account_project_scoped(tmp_path):
    a = DeleteReceipts(tmp_path, "a" * 64, P)
    a.record(M, "video")
    assert a.kind(M) == "video"
    assert a.kind(N) is None
    assert DeleteReceipts(tmp_path, "b" * 64, P).kind(M) is None
    assert DeleteReceipts(tmp_path, "a" * 64, N).kind(M) is None
    path = a.root / (M + ".json")
    assert path.stat().st_mode & 0o777 == 0o600
    path.write_text("{}")
    with pytest.raises(ValueError):
        a.kind(M)


def test_symlink_directory_cannot_supply_receipts(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (tmp_path / ".gflow_delete_receipts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        DeleteReceipts(tmp_path, "a" * 64, P)


def test_symlink_or_public_receipt_cannot_supply_ownership(tmp_path):
    a = DeleteReceipts(tmp_path, "a" * 64, P)
    a.record(M, "image")
    path = a.root / (M + ".json")
    path.chmod(0o644)
    with pytest.raises(ValueError):
        a.kind(M)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        a.kind(M)


@pytest.mark.parametrize(
    ("status", "url", "body"),
    [
        (200, "https://accounts.google.com/login", b"owner@example.com"),
        (403, "https://myaccount.google.com/u/0/", b"owner@example.com"),
        (200, "https://myaccount.google.com.evil/u/0/", b"owner@example.com"),
        (200, "https://myaccount.google.com/u/1/", b"owner@example.com"),
        (200, "https://myaccount.google.com/?authuser=1", b"owner@example.com"),
        (200, "https://myaccount.google.com/u/0/", b"one@example.com two@example.com"),
        (200, "https://myaccount.google.com/u/0/", b""),
    ],
)
async def test_unverified_identity_never_creates_receipt_scope(tmp_path, status, url, body):
    response = MagicMock(status=status, url=url, body=AsyncMock(return_value=body))
    page = MagicMock()
    page.context.request.get = AsyncMock(return_value=response)
    page.goto = AsyncMock()
    page.wait_for_function = AsyncMock()
    with pytest.raises(ValueError):
        await verified_delete_receipts(page, tmp_path, P)
    assert not (tmp_path / ".gflow_delete_receipts").exists()


async def test_unknown_project_never_creates_receipt_scope(tmp_path, monkeypatch):
    from gflow_cli.api import native_delete_receipts as module

    response = MagicMock(
        status=200,
        url="https://myaccount.google.com/u/0/",
        body=AsyncMock(return_value=b"owner@example.com"),
    )
    page = MagicMock()
    page.context.request.get = AsyncMock(return_value=response)
    page.goto = AsyncMock()
    page.wait_for_function = AsyncMock()
    monkeypatch.setattr(module, "native_rpc", AsyncMock(return_value=[[], None]))
    with pytest.raises(ValueError):
        await verified_delete_receipts(page, tmp_path, P)
    assert not (tmp_path / ".gflow_delete_receipts").exists()
