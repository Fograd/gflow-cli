from pathlib import Path

import pytest

from gflow_cli.api.transports.native_video_snapshot import snapshot_video

MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12


@pytest.mark.parametrize("rights", [False, None, 1, "true"])
def test_rights_refused_before_open(tmp_path, rights):
    with pytest.raises(ValueError, match="rights"):
        with snapshot_video(tmp_path / "missing.mp4", rights_confirmed=rights):
            pytest.fail("snapshot must not be exposed")


def test_snapshot_is_private_immutable_and_removed(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    with snapshot_video(source, rights_confirmed=True) as snapshot:
        assert snapshot != source
        assert snapshot.read_bytes() == MP4
        source.write_bytes(b"changed")
        assert snapshot.read_bytes() == MP4
        assert snapshot.stat().st_mode & 0o077 == 0
    assert not snapshot.exists()
    assert source.read_bytes() == b"changed"


def test_snapshot_removed_on_cancellation(tmp_path):
    import asyncio

    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    with pytest.raises(asyncio.CancelledError):
        with snapshot_video(source, rights_confirmed=True) as snapshot:
            raise asyncio.CancelledError
    assert not snapshot.exists()


def test_symlink_refused(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    link = tmp_path / "link.mp4"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        with snapshot_video(link, rights_confirmed=True):
            pytest.fail("symlink was accepted")


@pytest.mark.parametrize("data", [b"", b"not an mp4 header", b"\x00\x00\x00\x08ftypisom"])
def test_truncated_or_invalid_ftyp_refused(tmp_path, data):
    source = tmp_path / "source.mp4"
    source.write_bytes(data)
    with pytest.raises(ValueError):
        with snapshot_video(source, rights_confirmed=True):
            pytest.fail("invalid MP4 identification accepted")


def test_fifo_refused_without_open(tmp_path, monkeypatch):
    import os

    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO not available")
    source = tmp_path / "fifo.mp4"
    os.mkfifo(source)
    monkeypatch.setattr(os, "open", lambda *args: pytest.fail("FIFO must not be opened"))
    with pytest.raises(ValueError):
        with snapshot_video(source, rights_confirmed=True):
            pytest.fail("FIFO accepted")


def test_mutation_during_snapshot_refused(tmp_path, monkeypatch):
    import os

    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    original = os.read
    changed = False

    def mutate(fd, size):
        nonlocal changed
        chunk = original(fd, size)
        if not changed:
            changed = True
            source.write_bytes(MP4 + b"changed")
        return chunk

    monkeypatch.setattr(os, "read", mutate)
    with pytest.raises(ValueError, match="grew|changed"):
        with snapshot_video(source, rights_confirmed=True):
            pytest.fail("mutated source accepted")


def test_portable_missing_posix_open_flags(tmp_path, monkeypatch):
    import os

    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    monkeypatch.delattr(os, "O_NONBLOCK", raising=False)
    with snapshot_video(source, rights_confirmed=True) as snapshot:
        assert snapshot.read_bytes() == MP4


def test_cleanup_failure_preserves_cancellation(tmp_path, monkeypatch):
    import asyncio

    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    original = Path.unlink
    target = None

    def fail(path, *args, **kwargs):
        if path == target:
            raise OSError("SECRET private path")
        return original(path, *args, **kwargs)

    with pytest.raises(asyncio.CancelledError) as info:
        with snapshot_video(source, rights_confirmed=True) as target:
            monkeypatch.setattr(Path, "unlink", fail)
            raise asyncio.CancelledError()
    assert "cleanup pending" in info.value.__notes__[0]
    assert "SECRET" not in info.value.__notes__[0]
    monkeypatch.setattr(Path, "unlink", original)
    target.unlink()
    target.parent.rmdir()


def test_descriptor_close_fault_does_not_skip_cleanup_or_mask_cancellation(tmp_path, monkeypatch):
    import asyncio
    import os

    source = tmp_path / "source.mp4"
    source.write_bytes(MP4)
    close = os.close

    def failed(fd):
        close(fd)
        raise OSError("SECRET close")

    with pytest.raises(asyncio.CancelledError) as info:
        with snapshot_video(source, rights_confirmed=True) as target:
            monkeypatch.setattr(os, "close", failed)
            raise asyncio.CancelledError()
    assert not target.exists()
    assert "SECRET" not in repr(info.value.__notes__)
