import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.server import Settings, Store, create_app, validate_callback

AUTH = {"Authorization": "Bearer test-token"}


def settings(tmp_path):
    return Settings(
        token="test-token",
        root=tmp_path,
        accounts={
            "pro1": {"email": "test@example.org", "project": "11111111-1111-4111-8111-111111111111"}
        },
        callbacks=(),
        sync_wait=0,
    )


def test_auth_and_validation_do_not_enqueue(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        assert client.get("/v1/google-flow/accounts").status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        assert (
            client.post(
                "/v1/google-flow/images",
                headers=headers,
                json={"prompt": "x", "undefinedParameter": 7},
            ).status_code
            == 501
        )
        assert (
            client.post(
                "/v1/google-flow/images", headers=headers, json={"prompt": "x", "count": 0}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/google-flow/images", headers=headers, json={"prompt": "--output=/etc/passwd"}
            ).status_code
            == 200
        )
        assert len(client.get("/v1/google-flow/jobs", headers=headers).json()["jobs"]) == 1


def test_idempotency_and_restart_never_replay_running_job(tmp_path):
    cfg = settings(tmp_path)
    store = Store(cfg.root)
    first = store.submit("images", "pro1", {"prompt": "x"}, "unique")
    assert store.submit("images", "pro1", {"prompt": "x"}, "unique")["jobId"] == first["jobId"]
    with pytest.raises(ValueError):
        store.submit("images", "pro1", {"prompt": "changed"}, "unique")
    claimed = store.claim("pro1")
    assert claimed is not None
    assert store.claim("pro1") is None
    Store(cfg.root).recover()
    assert store.get(first["jobId"])["status"] == "interrupted"
    assert store.claim("pro1") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://callbacks.example/x",
        "https://callbacks.example.evil/x",
        "https://callbacks.example@127.0.0.1/x",
        "https://callbacks.example:443/x",
        "https://callbacks.example/x#fragment",
        "https://127.0.0.1/x",
    ],
)
def test_callbacks_reject_ssrf_and_credentials(url):
    with pytest.raises(ValueError):
        validate_callback(url, ("callbacks.example",))


def test_callback_exact_host():
    assert validate_callback("https://callbacks.example/path", ("callbacks.example",))


def test_cross_profile_reference_rejected(tmp_path):
    cfg = settings(tmp_path)
    cfg.accounts["pro2"] = {
        "email": "second@example.org",
        "project": cfg.accounts["pro1"]["project"],
    }
    with TestClient(create_app(cfg, start_workers=False)) as client:
        client.app.state.store.asset(
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "pro2",
            cfg.accounts["pro2"]["project"],
            str(tmp_path / "x.jpg"),
            "image/jpeg",
        )
        response = client.post(
            "/v1/google-flow/images",
            headers={"Authorization": "Bearer test-token"},
            json={
                "prompt": "x",
                "email": "test@example.org",
                "reference_1": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            },
        )
        assert response.status_code == 422


def test_download_rejects_unregistered_and_outside_files(tmp_path):
    cfg = settings(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        headers = {"Authorization": "Bearer test-token"}
        assert client.get("/v1/google-flow/assets/unknown", headers=headers).status_code == 404
        client.app.state.store.asset(
            "known", "pro1", cfg.accounts["pro1"]["project"], "/etc/passwd", "image/jpeg"
        )
        assert (
            client.get("/v1/google-flow/assets/known/download", headers=headers).status_code == 404
        )


def test_completed_inline_media_preserves_tee_contract(tmp_path):
    store = Store(tmp_path)
    job = store.submit("images", "pro1", {"prompt": "x"}, None)
    media = [{"mediaGenerationId": "x", "image": {"generatedImage": {"encodedImage": "aGk="}}}]
    store.finish(job["jobId"], "completed", {"media": media})
    assert store.get(job["jobId"])["media"] == media
    assert Store(tmp_path).get(job["jobId"])["status"] == "completed"


def test_streaming_json_limit_before_parse(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            content=iter([b'{"prompt":"', b"a" * 65536, b'"}']),
        )
        assert response.status_code == 413
        assert client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "x", "model": {}},
        {"prompt": "x", "model": []},
        {"prompt": "x", "replyUrl": True},
        {"prompt": "x", "replyUrl": {}},
        {"prompt": "x", "count": True},
    ],
)
def test_malformed_types_rejected_without_internal_errors(tmp_path, body):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert client.post("/v1/google-flow/images", headers=AUTH, json=body).status_code == 422


@pytest.mark.parametrize(
    "marker",
    ["@REFERENCE_1", "@Character_1", "@referenceImage_1", "@referenceAudio_1", "@referenceVideo_1"],
)
def test_unsupported_markers_rejected_before_generation(tmp_path, marker):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert (
            client.post(
                "/v1/google-flow/images", headers=AUTH, json={"prompt": "remake " + marker}
            ).status_code
            == 501
        )


def test_multi_profile_retry_keeps_original_account(tmp_path):
    cfg = settings(tmp_path)
    cfg.accounts["pro2"] = {
        "email": "second@example.org",
        "project": "22222222-2222-4222-8222-222222222222",
    }
    with TestClient(create_app(cfg, start_workers=False)) as client:
        headers = {**AUTH, "Idempotency-Key": "stable"}
        first = client.post("/v1/google-flow/images", headers=headers, json={"prompt": "x"})
        second = client.post("/v1/google-flow/images", headers=headers, json={"prompt": "x"})
        assert first.status_code == second.status_code == 200
        assert first.json()["jobId"] == second.json()["jobId"]
        assert len(client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"]) == 1


def test_one_running_job_per_profile(tmp_path):
    store = Store(tmp_path)
    first = store.submit("images", "pro1", {}, None)
    second = store.submit("images", "pro1", {}, None)
    assert store.claim("pro1")["id"] == first["jobId"]
    assert store.claim("pro1") is None
    store.finish(first["jobId"], "completed", {})
    assert store.claim("pro1")["id"] == second["jobId"]


def test_callbacks_persist_started_and_complete_result(tmp_path):
    store = Store(tmp_path)
    job = store.submit(
        "images", "pro1", {"replyUrl": "https://callbacks.example/x", "replyRef": "ref"}, None
    )
    store.claim("pro1")
    result = {"media": [{"image": {"generatedImage": {"encodedImage": "aGk="}}}]}
    store.finish(job["jobId"], "completed", result)
    with Store(tmp_path).connection() as conn:
        rows = list(conn.execute("SELECT state,payload FROM callbacks ORDER BY id"))
    import json

    assert [row["state"] for row in rows] == ["created", "started", "completed"]
    terminal = json.loads(rows[-1]["payload"])
    assert terminal["media"] == result["media"]
    assert terminal["replyRef"] == "ref"
    assert "createdAt" in terminal and "updatedAt" in terminal


def test_export_credit_free_route_and_extension_refusal(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        export = client.post(
            "/v1/google-flow/videos/gif",
            headers=AUTH,
            json={"mediaGenerationId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
        )
        assert export.status_code == 200
        cfg = settings(tmp_path)
        cfg.allow_video = True
        other = TestClient(create_app(cfg, start_workers=False))
        assert other.post("/v1/google-flow/videos/extend", headers=AUTH, json={}).status_code == 501


async def test_video_export_does_not_replace_source(tmp_path, monkeypatch):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    media = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    original = tmp_path / "source.mp4"
    original.write_bytes(b"original")
    store.asset(media, "pro1", cfg.accounts["pro1"]["project"], str(original), "video/mp4")
    job = store.submit(
        "videos/gif",
        "pro1",
        {
            "mediaGenerationId": media,
            "resolution": "270p",
            "project": cfg.accounts["pro1"]["project"],
        },
        None,
    )
    claimed = store.claim("pro1")

    async def fake_run(args, timeout, **kwargs):
        assert args[2:5] == ["gflow_cli.cli", "video", "upscale"]
        assert args[args.index("--scale") + 1] == "270p"
        path = tmp_path / "output" / job["jobId"] / "export.gif"
        path.write_bytes(b"GIF89a")
        return 0, b"Export saved"

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", fake_run)
    result = await execute(cfg, store, claimed)
    assert store.asset_get(media)["path"] == str(original)
    artifact = result["media"][0]["localArtifactId"]
    assert artifact != media
    assert store.asset_get(artifact)["mime"] == "image/gif"
    assert artifact in result["media"][0]["video"]["downloadPath"]


def test_queries_rejected_instead_of_ignored(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert client.get("/v1/google-flow/jobs?unknown=ignored", headers=AUTH).status_code == 501


def test_video_dto_validation_before_enqueue(tmp_path):
    cfg = settings(tmp_path)
    cfg.allow_video = True
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={"prompt": "x", "model": "veo-3.1-fast", "duration": 10},
        )
        assert response.status_code == 422
        assert client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"] == []


def test_system_voices_case_insensitive_and_custom_refused(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        listed = client.get("/v1/google-flow/voices?source=system", headers=AUTH)
        assert listed.status_code == 200
        voice = client.get("/v1/google-flow/voices/charon", headers=AUTH).json()
        assert voice["voice"] == voice["displayName"] == "Charon"
        assert voice["source"] == "system"
        assert client.get("/v1/google-flow/voices?source=user", headers=AUTH).status_code == 501
        assert client.post("/v1/google-flow/voices", headers=AUTH, json={}).status_code == 501


def test_openapi_requires_auth(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_workers=False)) as client:
        assert client.get("/openapi.json").status_code == 401
        schema = client.get("/openapi.json", headers=AUTH)
        assert schema.status_code == 200
        assert "/v1/google-flow/images" in schema.json()["paths"]


def test_concatenation_account_and_trim_validation(tmp_path):
    cfg = settings(tmp_path)
    cfg.accounts["pro2"] = {
        "email": "second@example.org",
        "project": cfg.accounts["pro1"]["project"],
    }
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for media, profile in (("first", "pro1"), ("second", "pro2")):
            path = tmp_path / (media + ".mp4")
            path.write_bytes(b"fixture")
            client.app.state.store.asset(
                media, profile, cfg.accounts[profile]["project"], str(path), "video/mp4"
            )
        assert (
            client.post(
                "/v1/google-flow/videos/concatenate",
                headers=AUTH,
                json={"media": [{"mediaGenerationId": "first"}, {"mediaGenerationId": "second"}]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/google-flow/videos/concatenate",
                headers=AUTH,
                json={
                    "media": [
                        {"mediaGenerationId": "first", "trimStart": -1},
                        {"mediaGenerationId": "first"},
                    ]
                },
            ).status_code
            == 422
        )
        assert client.get("/v1/google-flow/jobs", headers=AUTH).json()["jobs"] == []


async def test_concatenation_result_is_local_and_preserves_sources(tmp_path, monkeypatch):
    from gflow_cli.selfhost.concatenate import ConcatenateResult

    cfg = settings(tmp_path)
    store = Store(tmp_path)
    path = tmp_path / "source.mp4"
    path.write_bytes(b"source")
    store.asset("original", "pro1", cfg.accounts["pro1"]["project"], str(path), "video/mp4")
    store.submit(
        "videos/concatenate",
        "pro1",
        {
            "project": cfg.accounts["pro1"]["project"],
            "media": [{"mediaGenerationId": "original", "trimStart": 0, "trimEnd": 0}] * 2,
        },
        None,
    )

    async def fake_concatenate(clips, output, timeout_s):
        assert all(clip.path == path for clip in clips)
        output.write_bytes(b"concatenated")
        return ConcatenateResult(path=output, bytes=12, duration=2, width=160, height=90)

    monkeypatch.setattr("gflow_cli.selfhost.concatenate.execute", fake_concatenate)
    result = await execute(cfg, store, store.claim("pro1"))
    assert result["backend"] == "local-ffmpeg"
    assert result["localArtifactId"].startswith("local_")
    assert "mediaGenerationId" not in result
    assert "encodedVideo" in result
    assert store.asset_get("original")["path"] == str(path)
    assert store.asset_get(result["localArtifactId"])["project"] == ""
