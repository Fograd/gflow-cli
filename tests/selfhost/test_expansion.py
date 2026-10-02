import asyncio
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.server import create_app
from gflow_cli.selfhost.store import Store

AUTH = {"Authorization": "Bearer test-token"}
PROJECT = "11111111-1111-4111-8111-111111111111"


def settings(tmp_path):
    cfg = Settings(
        token="test-token",
        root=tmp_path,
        accounts={"pro1": {"email": "first", "project": PROJECT}},
        allow_video=True,
    )
    cfg.sync_wait = 0
    return cfg


def add_image(store, root, media, profile="pro1"):
    path = root / (media + ".jpg")
    path.write_bytes(b"\xff\xd8\xfffixture")
    store.asset(media, profile, PROJECT, str(path), "image/jpeg")
    return path


def test_video_i2v_and_r2v_validation(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        ids = [str(uuid.uuid4()) for _ in range(4)]
        for media in ids:
            add_image(client.app.state.store, tmp_path, media)
        i2v = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "prompt": "motion",
                "startImage": ids[0],
                "endImage": ids[1],
                "count": 2,
                "async": True,
            },
        )
        assert i2v.status_code == 200
        r2v = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "prompt": "motion",
                "referenceImage_1": ids[0],
                "referenceImage_2": ids[1],
                "async": True,
            },
        )
        assert r2v.status_code == 200
        too_many = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={
                "prompt": "motion",
                **{f"referenceImage_{i + 1}": ref for i, ref in enumerate(ids)},
            },
        )
        assert too_many.status_code == 422
        assert (
            client.post(
                "/v1/google-flow/videos",
                headers=AUTH,
                json={"prompt": "motion", "endImage": ids[0]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/google-flow/videos",
                headers=AUTH,
                json={"prompt": "motion", "startImage": ids[0], "referenceImage_1": ids[1]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/google-flow/videos",
                headers=AUTH,
                json={"prompt": "motion", "resolution": "360p", "model": "veo-3.1-fast"},
            ).status_code
            == 422
        )


async def test_i2v_cli_uses_owned_files_and_one_output(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    start_id, end_id = str(uuid.uuid4()), str(uuid.uuid4())
    start, end = add_image(store, tmp_path, start_id), add_image(store, tmp_path, end_id)
    job = store.submit(
        "videos",
        "pro1",
        {
            "prompt": "--danger",
            "project": PROJECT,
            "model": "omni-flash",
            "aspectRatio": "16:9",
            "count": 1,
            "startImage": start_id,
            "endImage": end_id,
            "resolution": "360p",
            "duration": 10,
        },
        None,
    )

    async def run(args, timeout):
        assert args[3:5] == ["video", "i2v"]
        assert args[args.index("--initial-frame") + 1] == str(start)
        assert args[args.index("--end-frame") + 1] == str(end)
        assert args[args.index("--resolution") + 1] == "360p"
        assert args[-2:] == ["--", "--danger"]
        output = tmp_path / "output" / job["jobId"] / "video.mp4"
        output.write_bytes(b"video")
        return 0, json.dumps(
            {"status": "ok", "media_id": str(uuid.uuid4()), "local_path": str(output)}
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, store.claim("pro1"))
    assert len(result["media"]) == 1


async def test_multi_video_crash_keeps_completed_checkpoint(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    job = store.submit(
        "videos",
        "pro1",
        {
            "prompt": "motion",
            "project": PROJECT,
            "model": "veo-3.1-fast",
            "aspectRatio": "16:9",
            "count": 3,
        },
        None,
    )
    calls = 0

    async def run(args, timeout):
        nonlocal calls
        calls += 1
        assert args[args.index("--count") + 1] == "1"
        if calls == 2:
            raise asyncio.CancelledError
        output = tmp_path / "output" / job["jobId"] / "part-1" / "video.mp4"
        output.write_bytes(b"video")
        return 0, json.dumps(
            {"status": "ok", "media_id": str(uuid.uuid4()), "local_path": str(output)}
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    with pytest.raises(asyncio.CancelledError):
        await execute(cfg, store, store.claim("pro1"))
    assert len(store.get(job["jobId"])["media"]) == 1
    Store(tmp_path).recover()
    assert store.get(job["jobId"])["status"] == "interrupted"
    assert len(store.get(job["jobId"])["media"]) == 1
    assert store.claim("pro1") is None


def test_sync_wait_and_async_immediate(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    cfg.sync_wait = 1

    async def fake_execute(cfg, store, job):
        await asyncio.sleep(0.02)
        return {"media": []}

    monkeypatch.setattr("gflow_cli.selfhost.runtime.execute", fake_execute)
    with TestClient(create_app(cfg)) as client:
        response = client.post(
            "/v1/google-flow/images", headers=AUTH, json={"prompt": "x", "async": False}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        response = client.post(
            "/v1/google-flow/images", headers=AUTH, json={"prompt": "x", "async": True}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "created"


async def test_cancelled_sync_wait_keeps_idempotent_job(tmp_path):
    cfg = settings(tmp_path)
    cfg.sync_wait = 10
    app = create_app(cfg, start_workers=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = {**AUTH, "Idempotency-Key": "unchanged"}
        task = asyncio.create_task(
            client.post(
                "/v1/google-flow/images", headers=headers, json={"prompt": "x", "async": False}
            )
        )
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        accepted = await client.post(
            "/v1/google-flow/images", headers=headers, json={"prompt": "x", "async": True}
        )
        assert accepted.status_code == 200
        assert len(app.state.store.jobs()) == 1


def test_job_filter_pagination_and_raw_asset(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        store = client.app.state.store
        for index in range(3):
            store.submit("images", "pro1", {"prompt": str(index)}, None)
        first = client.get("/v1/google-flow/jobs?limit=2&status=created&email=first", headers=AUTH)
        assert first.status_code == 200
        assert len(first.json()["jobs"]) == 2
        cursor = first.json()["cursor"]
        second = client.get(
            "/v1/google-flow/jobs", params={"limit": 2, "cursor": cursor}, headers=AUTH
        )
        assert len(second.json()["jobs"]) == 1
        image = str(uuid.uuid4())
        add_image(store, tmp_path, image)
        assert client.get(
            f"/v1/google-flow/assets/{image}?raw=true", headers=AUTH
        ).content.startswith(b"\xff\xd8\xff")
        assert client.get("/v1/google-flow/jobs?limit=10001", headers=AUTH).status_code == 422


def test_registered_account_pending_and_safe_unregistration(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    home = tmp_path / "profiles"
    profile = home / "profile_pro2"
    profile.mkdir(parents=True)
    monkeypatch.setattr("gflow_cli.auth.default_profile_root", lambda: home)
    monkeypatch.setattr("gflow_cli.auth.profile_dir", lambda name: home / ("profile_" + name))
    with TestClient(create_app(cfg, start_workers=False)) as client:
        registered = client.post(
            "/v1/google-flow/accounts",
            headers=AUTH,
            json={"profile": "pro2", "email": "second", "projectId": PROJECT},
        )
        assert registered.status_code == 200
        assert registered.json()["health"] == "LOGIN_REQUIRED"
        assert (
            client.post(
                "/v1/google-flow/images", headers=AUTH, json={"prompt": "x", "email": "second"}
            ).status_code
            == 422
        )
        assert client.delete("/v1/google-flow/accounts/second", headers=AUTH).status_code == 200
        assert profile.is_dir()
        store = client.app.state.store
        store.submit("images", "pro1", {}, None)
        assert client.delete("/v1/google-flow/accounts/first", headers=AUTH).status_code == 409


def test_local_delete_refuses_active_references(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        store = client.app.state.store
        media = str(uuid.uuid4())
        path = add_image(store, tmp_path, media)
        body = {"mediaGenerationIds": [media], "localOnly": True}
        store.submit("images", "pro1", {"reference_1": media}, None)
        assert (
            client.request(
                "DELETE", "/v1/google-flow/assets/first", headers=AUTH, json=body
            ).status_code
            == 409
        )
        assert path.is_file()
        job = store.claim("pro1")
        store.finish(job["id"], "failed", {})
        response = client.request("DELETE", "/v1/google-flow/assets/first", headers=AUTH, json=body)
        assert response.status_code == 200
        assert response.json()["scope"] == "local-cache"
        assert not path.exists()


def test_captcha_token_retry_and_one_shot_ownership(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        payload = {"prompt": "test", "captchaToken": "a" * 30, "async": True}
        headers = {**AUTH, "Idempotency-Key": "captcha-once"}
        first = client.post("/v1/google-flow/images", headers=headers, json=payload)
        assert first.status_code == 200
        job_id = first.json()["jobId"]
        files = list((tmp_path / "captcha-input").glob("*.token"))
        assert len(files) == 1
        assert (
            client.post("/v1/google-flow/images", headers=headers, json=payload).json()["jobId"]
            == job_id
        )
        files[0].unlink()
        client.app.state.store.finish(job_id, "completed", {"media": []})
        replay = client.post("/v1/google-flow/images", headers=headers, json=payload)
        assert replay.status_code == 200 and replay.json()["jobId"] == job_id
        assert not list((tmp_path / "captcha-input").glob("*.token"))
        assert client.post("/v1/google-flow/images", headers=AUTH, json=payload).status_code == 409
        assert not list((tmp_path / "captcha-input").glob("*.token"))


def test_captcha_validation_and_queue_rejection_leave_no_secret(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        payload = {"prompt": "test", "captchaToken": "b" * 30, "async": True}
        bad = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={**payload, "replyUrl": "https://disallowed.example/test"},
        )
        assert bad.status_code == 422
        assert not list((tmp_path / "captcha-input").glob("*.token"))

        def full(*args, **kwargs):
            raise OverflowError("full")

        monkeypatch.setattr(client.app.state.store, "submit", full)
        assert client.post("/v1/google-flow/images", headers=AUTH, json=payload).status_code == 429
        assert not list((tmp_path / "captcha-input").glob("*.token"))


def test_shared_cache_bytes_and_active_input_survive_delete(tmp_path):
    store = Store(tmp_path)
    path = tmp_path / "shared.jpg"
    path.write_bytes(b"fixture")
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for identifier in ids:
        store.asset(identifier, "pro1", PROJECT, str(path), "image/jpeg")
    assert store.asset_delete(ids[0]) is None
    assert path.exists()
    store.submit("assets", "pro1", {"input": str(path), "project": PROJECT}, None)
    assert store.asset_delete(ids[1]) is None
    assert path.exists()


async def test_native_video_upload_and_archive_worker_contract(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisomfixture")
    media_id = str(uuid.uuid4())
    seen = []

    async def run(args, timeout):
        seen.append(args)
        if args[3] == "upload-video":
            return 0, json.dumps({"status": "ok", "media_id": media_id}).encode()
        return 0, json.dumps({"status": "ok", "deleted": [media_id]}).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    upload = store.submit(
        "assets",
        "pro1",
        {"input": str(path), "mime": "video/mp4", "project": PROJECT, "rightsConfirmed": True},
        None,
    )
    result = await execute(cfg, store, store.claim("pro1"))
    assert result["mediaGenerationId"]["mediaGenerationId"] == media_id
    assert store.asset_get(media_id)["mime"] == "video/mp4"
    store.finish(upload["jobId"], "completed", result)
    store.submit(
        "assets/archive", "pro1", {"project": PROJECT, "mediaGenerationIds": [media_id]}, None
    )
    archived = await execute(cfg, store, store.claim("pro1"))
    assert archived["operation"] == "archive" and archived["localCacheModified"] is False
    assert path.exists() and store.asset_get(media_id)["path"] == str(path)
    assert seen[0][3] == "upload-video" and seen[1][3] == "media-delete"
    assert json.loads(seen[0][5])["rights_confirmed"] is True


def test_remote_archive_is_durable_and_validated(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        payload = {"projectId": PROJECT, "mediaGenerationIds": [str(uuid.uuid4())], "async": True}
        accepted = client.request(
            "DELETE", "/v1/google-flow/assets/first", headers=AUTH, json=payload
        )
        assert accepted.status_code == 200
        assert client.app.state.store.get(accepted.json()["jobId"])["status"] == "created"
        invalid = client.request(
            "DELETE",
            "/v1/google-flow/assets/first",
            headers=AUTH,
            json={**payload, "projectId": "bad"},
        )
        assert invalid.status_code == 422


def test_native_media_read_has_useapi_ids_and_local_scope_is_default(tmp_path, monkeypatch):
    media_id = str(uuid.uuid4())
    calls = []

    async def run(args, timeout):
        calls.append(args)
        return 0, json.dumps(
            {
                "status": "ok",
                "media": [
                    {"media_id": media_id, "project_id": PROJECT, "batch_media_ids": [media_id]}
                ],
            }
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        local = client.get("/v1/google-flow/assets/media/first", headers=AUTH)
        assert local.status_code == 200 and not calls
        native = client.get(
            "/v1/google-flow/assets/media/first?source=google&limit=1", headers=AUTH
        )
        assert native.status_code == 200
        assert native.json()["media"][0]["mediaGenerationId"] == media_id
        assert native.json()["scope"] == "google-project-library"
        assert calls[0][3] == "media-list"
        invalid = client.get("/v1/google-flow/assets/media/first?source=invalid", headers=AUTH)
        assert invalid.status_code == 422


def test_upload_rights_header_rejected_before_bytes_or_queue(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        for mime, rights in (
            ("video/mp4", "yes"),
            ("video/mp4", "TRUE"),
            ("image/png", "true"),
            ("image/jpeg", "false"),
        ):
            response = client.post(
                "/v1/google-flow/assets",
                headers={**AUTH, "Content-Type": mime, "X-Flow-Rights-Confirmed": rights},
                content=b"fixture",
            )
            assert response.status_code == 422
        assert not (tmp_path / "uploads").exists()
        assert client.app.state.store.job_page(limit=100)["jobs"] == []


async def test_native_video_rights_required_has_safe_remedy(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fixture")

    async def run(args, timeout):
        assert json.loads(args[5])["rights_confirmed"] is False
        return 0, json.dumps(
            {"status": "error", "code": "upload_rights_required", "detail": "untrusted detail"}
        ).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    store.submit(
        "assets", "pro1", {"input": str(path), "mime": "video/mp4", "project": PROJECT}, None
    )
    result = await execute(cfg, store, store.claim("pro1"))
    assert result["error"]["code"] == "upload_rights_required"
    assert "X-Flow-Rights-Confirmed" in result["error"]["detail"]
    assert "untrusted detail" not in result["error"]["detail"]
