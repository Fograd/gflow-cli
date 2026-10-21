"""Local upload storage failures must not poison shared hash-named references."""

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.server import create_app
from tests.selfhost.test_server import AUTH, settings

PNG = b"\x89PNG\r\n\x1a\nlocal-storage-only-test"


def upload_path(root):
    return root / "uploads" / (hashlib.sha256(PNG).hexdigest() + ".png")


@pytest.fixture
def uploads(monkeypatch):
    seen = []

    async def execute(cfg, store, job):
        payload = json.loads(job["payload"])
        seen.append(Path(payload["input"]).read_bytes())
        return {"uploaded": True}

    monkeypatch.setattr("gflow_cli.selfhost.runtime.execute", execute)
    return seen


def post(client):
    return client.post(
        "/v1/google-flow/assets/test@example.org",
        headers={**AUTH, "Content-Type": "image/png"},
        content=PNG,
    )


def test_verified_cached_bytes_are_reused_without_truncating_them(tmp_path, uploads):
    path = upload_path(tmp_path)
    path.parent.mkdir()
    path.write_bytes(PNG)
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = path.stat()
    with TestClient(create_app(settings(tmp_path))) as client:
        assert post(client).status_code == 200
    assert uploads == [PNG]
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert path.stat().st_ino == before.st_ino


@pytest.mark.parametrize("old", [None, b"", b"x" * len(PNG)])
def test_fsync_failure_refuses_before_queueing_and_keeps_previous_cache(
    tmp_path, monkeypatch, uploads, old
):
    path = upload_path(tmp_path)
    path.parent.mkdir()
    if old is not None:
        path.write_bytes(old)

    def full(descriptor):
        raise OSError(errno.ENOSPC, "No space left on device")

    with TestClient(create_app(settings(tmp_path))) as client:
        monkeypatch.setattr(os, "fsync", full)
        response = post(client)
        assert response.status_code == 507, response.text
        assert response.json()["detail"] == "Upload storage unavailable; no job was queued"
        assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []
    assert uploads == []
    assert path.read_bytes() == old if old is not None else not path.exists()
    assert list(path.parent.iterdir()) == ([path] if old is not None else [])


@pytest.mark.parametrize("old", [b"", b"x" * len(PNG)])
def test_corrupt_cache_is_replaced_atomically_only_after_full_bytes_are_synced(
    tmp_path, monkeypatch, uploads, old
):
    path = upload_path(tmp_path)
    path.parent.mkdir()
    path.write_bytes(old)
    original_replace = os.replace
    replacements = []

    def replace(source, destination):
        if Path(destination) == path:
            assert path.read_bytes() == old
            assert Path(source).read_bytes() == PNG
            assert Path(source).parent == path.parent
            replacements.append(source)
        return original_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    with TestClient(create_app(settings(tmp_path))) as client:
        assert post(client).status_code == 200
    assert len(replacements) == 1
    assert uploads == [PNG]
    assert path.read_bytes() == PNG
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(path.parent.iterdir()) == [path]


def test_partial_write_failure_removes_only_temporary_bytes_before_queueing(
    tmp_path, monkeypatch, uploads
):
    path = upload_path(tmp_path)
    original_temporary = tempfile.NamedTemporaryFile

    def temporary(*args, **kwargs):
        output = original_temporary(*args, **kwargs)

        def partial(data):
            output.file.write(data[:1])
            output.file.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

        output.write = partial
        return output

    with TestClient(create_app(settings(tmp_path))) as client:
        monkeypatch.setattr(tempfile, "NamedTemporaryFile", temporary)
        response = post(client)
        assert response.status_code == 507
        assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []
    assert uploads == []
    assert not path.exists()
    assert list(path.parent.iterdir()) == []


def test_atomic_replace_failure_preserves_previous_reference_and_cleans_temporary_file(
    tmp_path, monkeypatch, uploads
):
    path = upload_path(tmp_path)
    path.parent.mkdir()
    path.write_bytes(b"old-cache")

    def unavailable(source, destination):
        raise OSError(errno.ENOSPC, "No space left on device")

    with TestClient(create_app(settings(tmp_path))) as client:
        monkeypatch.setattr(os, "replace", unavailable)
        assert post(client).status_code == 507
        assert client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"] == []
    assert uploads == []
    assert path.read_bytes() == b"old-cache"
    assert list(path.parent.iterdir()) == [path]
