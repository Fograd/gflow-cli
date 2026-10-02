import asyncio
import json
import os
import uuid
from types import SimpleNamespace

import pytest

from gflow_cli.image_recovery import (
    ImageJournal,
    ImagePartialDownloadError,
    download_images,
    read_journal,
)


def images():
    return [
        SimpleNamespace(
            media_name=str(uuid.uuid4()), workflow_id=str(uuid.uuid4()), seed=i, dimensions=(8, 8)
        )
        for i in range(2)
    ]


def test_second_download_keeps_all_handles_and_first_path(tmp_path, monkeypatch):
    invocation = str(uuid.uuid4())
    monkeypatch.setenv("GFLOW_IMAGE_RECOVERY_ID", invocation)
    output = images()

    class Client:
        async def download_image(self, image, target):
            if image is output[1]:
                raise RuntimeError("https://signed.example/private?token=secret")
            target.write_bytes(b"first")
            return target

    with pytest.raises(ImagePartialDownloadError) as caught:
        asyncio.run(download_images(Client(), output, [tmp_path / "one.jpg", tmp_path / "two.jpg"]))
    snapshot = read_journal(tmp_path, invocation)
    assert [item["media_name"] for item in snapshot["images"]] == [x.media_name for x in output]
    assert snapshot["images"][0]["local_path"] == str(tmp_path / "one.jpg")
    assert "local_path" not in snapshot["images"][1]
    assert "secret" not in json.dumps(caught.value.to_problem_details())
    journal = tmp_path / ".gflow-image-recovery" / (invocation + ".json")
    assert journal.stat().st_mode & 0o777 == 0o600


def test_journal_rejects_stale_symlink_oversize_and_escape(tmp_path):
    invocation = str(uuid.uuid4())
    journal = ImageJournal(tmp_path, images(), invocation=invocation)
    assert read_journal(tmp_path, str(uuid.uuid4())) == {}
    raw = json.loads(journal.path.read_text())
    raw["invocation"] = str(uuid.uuid4())
    journal.path.write_text(json.dumps(raw))
    assert read_journal(tmp_path, invocation) == {}
    journal.path.unlink()
    outside = tmp_path.parent / (invocation + ".json")
    outside.write_text("{}")
    journal.path.symlink_to(outside)
    assert read_journal(tmp_path, invocation) == {}
    with pytest.raises(ValueError):
        ImageJournal(tmp_path, images(), invocation=invocation)
    journal.path.unlink()
    journal.path.write_bytes(b" " * 65537)
    assert read_journal(tmp_path, invocation) == {}
    journal.path.unlink()
    journal = ImageJournal(tmp_path, images(), invocation=invocation)
    with pytest.raises(ValueError):
        journal.complete(0, outside)


def queued(tmp_path):
    from gflow_cli.selfhost.config import Settings
    from gflow_cli.selfhost.store import Store

    project = str(uuid.uuid4())
    cfg = Settings(
        token="test", root=tmp_path, accounts={"pro1": {"email": "first", "project": project}}
    )
    store = Store(tmp_path)
    job = store.submit(
        "images",
        "pro1",
        {
            "project": project,
            "prompt": "fixture",
            "count": 2,
            "model": "nano-banana-2",
            "aspectRatio": "square",
        },
        None,
    )
    claimed = store.claim("pro1")
    return cfg, store, claimed, job["jobId"]


@pytest.mark.parametrize("outcome", ["nonzero", "timeout", "cancel", "restart"])
def test_subprocess_failure_and_restart_preserve_download_without_resubmit(
    tmp_path, monkeypatch, outcome
):
    from gflow_cli.selfhost.runtime import execute

    cfg, store, job, identifier = queued(tmp_path)
    output = images()
    out = tmp_path / "output" / identifier
    out.mkdir(parents=True)
    journal = ImageJournal(out, output, invocation=identifier)
    first = out / "first.jpg"
    first.write_bytes(b"first-image")
    journal.complete(0, first)
    calls = []

    async def fail(args, timeout, **kwargs):
        calls.append(args)
        assert kwargs["image_recovery_id"] == identifier
        if outcome == "timeout":
            raise TimeoutError()
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return 6, b"private URL/token should never be exposed"

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", fail)
    if outcome == "restart":
        store.recover()
        assert store.get(identifier)["status"] == "interrupted"
        assert calls == []
    elif outcome in ("timeout", "cancel"):
        with pytest.raises(TimeoutError if outcome == "timeout" else asyncio.CancelledError):
            asyncio.run(execute(cfg, store, job))
        assert len(calls) == 1
        store.recover()
    else:
        result = asyncio.run(execute(cfg, store, job))
        store.finish(identifier, "failed", result)
        assert len(calls) == 1
    result = store.get(identifier)
    assert result["knownMediaGenerationIds"] == [item.media_name for item in output]
    assert result["completedCount"] == 1
    assert result["media"][0]["mediaGenerationId"] == output[0].media_name
    assert store.asset_get(output[0].media_name)["path"] == str(first)
    assert store.claim("pro1") is None
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("fault", ["missing", "invalid", "oversize"])
def test_later_invalid_output_keeps_first_checkpoint(tmp_path, monkeypatch, fault):
    from gflow_cli.selfhost.config import MAX_ASSET
    from gflow_cli.selfhost.runtime import execute

    cfg, store, job, identifier = queued(tmp_path)
    out = tmp_path / "output" / identifier
    out.mkdir(parents=True)
    output = images()
    first, second = out / "first.jpg", out / "second.jpg"
    first.write_bytes(b"first-image")
    if fault != "missing":
        second.write_bytes(b"second-image")
    if fault == "oversize":
        with second.open("wb") as file:
            file.truncate(MAX_ASSET + 1)
    items = [
        {"media_name": image.media_name, "local_path": str(path)}
        for image, path in zip(output, (first, second), strict=True)
    ]
    if fault == "invalid":
        items[1]["media_name"] = "invalid handle"

    async def result(args, timeout, **kwargs):
        return 0, json.dumps({"status": "completed", "images": items}).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", result)
    with pytest.raises(ValueError):
        asyncio.run(execute(cfg, store, job))
    store.finish(
        identifier, "failed", {"error": {"code": "invalid_operation_result", "retryable": False}}
    )
    result = store.get(identifier)
    assert result["media"][0]["mediaGenerationId"] == output[0].media_name
    assert result["completedCount"] == 1
    assert result["knownMediaGenerationIds"][0] == output[0].media_name


def test_recovered_oversize_file_remains_available_for_protected_download(tmp_path, monkeypatch):
    from gflow_cli.selfhost.config import MAX_ASSET
    from gflow_cli.selfhost.runtime import execute

    cfg, store, job, identifier = queued(tmp_path)
    out = tmp_path / "output" / identifier
    out.mkdir(parents=True)
    output = images()
    journal = ImageJournal(out, output, invocation=identifier)
    first = out / "large.jpg"
    with first.open("wb") as file:
        file.truncate(MAX_ASSET + 1)
    journal.complete(0, first)

    async def result(args, timeout, **kwargs):
        return 0, json.dumps(
            {
                "status": "completed",
                "images": [{"media_name": output[0].media_name, "local_path": str(first)}],
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", result)
    with pytest.raises(ValueError):
        asyncio.run(execute(cfg, store, job))
    saved = store.get(identifier)
    assert saved["completedCount"] == 1
    assert saved["media"][0]["downloadPath"].endswith("/download")


def test_missing_download_return_is_partial_not_success(tmp_path):
    output = images()

    class Client:
        async def download_image(self, image, path):
            return path

    with pytest.raises(ImagePartialDownloadError) as caught:
        asyncio.run(download_images(Client(), output, [tmp_path / "one.jpg", tmp_path / "two.jpg"]))
    assert len(caught.value.recovery["images"]) == 2
    assert all("local_path" not in item for item in caught.value.recovery["images"])


def test_recovery_does_not_import_symlink_file_or_parent_escape(tmp_path):
    invocation = str(uuid.uuid4())
    output = images()
    journal = ImageJournal(tmp_path, output, invocation=invocation)
    outside = tmp_path.parent / (invocation + ".jpg")
    outside.write_bytes(b"outside")
    (tmp_path / "link.jpg").symlink_to(outside)
    data = journal.data
    data["images"][0]["relative_path"] = "link.jpg"
    data["images"][1]["relative_path"] = "../" + outside.name
    journal.path.write_text(json.dumps(data))
    recovered = read_journal(tmp_path, invocation)
    assert len(recovered["images"]) == 2
    assert all("local_path" not in item for item in recovered["images"])


def test_manifest_download_partial_preserves_images_and_completed_path(tmp_path):
    from gflow_cli.api.dto import BatchSubmissionResult
    from gflow_cli.image_batch import BatchPromptItem, _download_results

    output = images()

    class Client:
        async def download_image(self, image, target):
            if image is output[1]:
                raise RuntimeError("signed-url-secret")
            target.write_bytes(b"first")
            return target

    result = BatchSubmissionResult(
        status="ok", project_id="project", prompt_idx=0, prompt_hash="hash", images=tuple(output)
    )
    rows = asyncio.run(
        _download_results(
            client=Client(),
            prompts=(BatchPromptItem("fixture", count=2),),
            results=[result],
            output_dir=tmp_path,
            profile_name=None,
            profile_dir=None,
            recorder=None,
            continue_on_error=True,
        )
    )
    assert rows[0].status == "fail"
    assert len(rows[0].saved_paths) == 1
    assert [item.media_name for item in rows[0].images] == [item.media_name for item in output]
    assert "secret" not in rows[0].error


def test_later_corrupt_journal_record_does_not_discard_first_handle(tmp_path):
    invocation = str(uuid.uuid4())
    output = images()
    journal = ImageJournal(tmp_path, output, invocation=invocation)
    journal.data["images"][1]["media_name"] = "https://private.invalid/token"
    journal.path.write_text(json.dumps(journal.data))
    result = read_journal(tmp_path, invocation)
    assert result["images"][0]["media_name"] == output[0].media_name
    assert len(result["images"]) == 1


def test_journal_portable_without_posix_flags_or_fchmod(tmp_path, monkeypatch):
    for name in ("O_NOFOLLOW", "O_DIRECTORY", "fchmod"):
        monkeypatch.delattr(os, name, raising=False)
    invocation = str(uuid.uuid4())
    output = images()
    journal = ImageJournal(tmp_path, output, invocation=invocation)
    path = tmp_path / "first.jpg"
    path.write_bytes(b"first")
    journal.complete(0, path)
    assert read_journal(tmp_path, invocation)["images"][0]["local_path"] == str(path)
    journal.path.unlink()
    journal.path.symlink_to(path)
    assert read_journal(tmp_path, invocation) == {}


def test_journal_refuses_symlink_private_directory(tmp_path):
    (tmp_path / ".gflow-image-recovery").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError):
        ImageJournal(tmp_path, images())


def test_journal_metadata_allowlist_drops_untrusted_values(tmp_path):
    output = [
        SimpleNamespace(
            media_name=str(uuid.uuid4()),
            workflow_id="",
            seed="private-token",
            dimensions=("secret", 2),
            prompt="private-prompt",
            fife_url="signed-url",
        )
    ]
    journal = ImageJournal(tmp_path, output)
    assert set(json.loads(journal.path.read_text())["images"][0]) == {"media_name"}


def test_empty_workflow_still_downloads_without_inventing_handle(tmp_path):
    output = [
        SimpleNamespace(media_name=str(uuid.uuid4()), workflow_id="", seed=42, dimensions=(8, 8))
    ]

    class Client:
        async def download_image(self, image, target):
            target.write_bytes(b"actual-image")
            return target

    path = tmp_path / "image.jpg"
    assert asyncio.run(download_images(Client(), output, [path])) == [path]
    journals = list((tmp_path / ".gflow-image-recovery").glob("*.json"))
    recorded = read_journal(tmp_path, journals[0].stem)["images"][0]
    assert recorded["media_name"] == output[0].media_name
    assert "workflow_id" not in recorded
    assert recorded["local_path"] == str(path)


@pytest.mark.parametrize("fault", ["initial-write", "second-fsync", "initial-callback"])
def test_storage_fault_reports_known_handles_without_second_transfer(tmp_path, monkeypatch, fault):
    output = images()
    calls = []

    class Client:
        async def download_image(self, image, target):
            calls.append(image)
            target.write_bytes(b"actual-image")
            return target

    callback = None
    if fault == "initial-write":
        monkeypatch.setattr(
            ImageJournal, "_write", lambda *_: (_ for _ in ()).throw(OSError("private path"))
        )
    elif fault == "second-fsync":
        actual = os.fsync
        count = 0

        def fsync(fd):
            nonlocal count
            count += 1
            if count > 2:
                raise OSError("private fsync detail")
            return actual(fd)

        monkeypatch.setattr(os, "fsync", fsync)
    else:

        def callback(*_):
            raise OSError("private checkpoint detail")

    with pytest.raises(ImagePartialDownloadError) as caught:
        asyncio.run(
            download_images(
                Client(),
                output,
                [tmp_path / "first.jpg", tmp_path / "second.jpg"],
                on_checkpoint=callback,
            )
        )
    assert [entry["media_name"] for entry in caught.value.recovery["images"]] == [
        entry.media_name for entry in output
    ]
    assert len(calls) == (1 if fault == "second-fsync" else 0)
    if fault == "second-fsync":
        assert caught.value.recovery["images"][0]["local_path"] == str(tmp_path / "first.jpg")
    assert caught.value.retryable is False
    assert "private" not in json.dumps(caught.value.to_problem_details())


def test_nonzero_stdout_handles_survive_missing_journal_without_raw_error_copy(
    tmp_path, monkeypatch
):
    from gflow_cli.selfhost.runtime import execute

    cfg, store, job, identifier = queued(tmp_path)
    output = images()

    async def failure(*args, **kwargs):
        return 6, json.dumps(
            {
                "status": "fail",
                "error": {
                    "detail": "raw-secret",
                    "imageRecovery": {
                        "images": [
                            {"media_name": item.media_name, "signedUrl": "secret-url"}
                            for item in output
                        ]
                    },
                },
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", failure)
    result = asyncio.run(execute(cfg, store, job))
    store.finish(identifier, "failed", result)
    persisted = store.get(identifier)
    assert persisted["knownMediaGenerationIds"] == [entry.media_name for entry in output]
    assert "secret" not in json.dumps(persisted)
