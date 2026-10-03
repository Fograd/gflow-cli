import json

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app

AUTH = {"Authorization": "Bearer test-token"}
PROJECT = "11111111-1111-4111-8111-111111111111"


def cfg(tmp_path):
    return Settings(
        token="test-token",
        root=tmp_path,
        accounts={"pro1": {"email": "fixture", "project": PROJECT}},
        allow_video=True,
        callbacks=("callbacks.example",),
        sync_wait=0,
    )


def test_video_async_201_and_poll_identity(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos",
            headers=AUTH,
            json={"prompt": "x", "async": True, "replyRef": "caller"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["jobid"] == body["jobId"]
        assert body["type"] == "video" and body["status"] == "created"
        assert body["request"]["async"] is True
        assert body["request"]["replyRef"] == "caller"
        assert body["created"].endswith("Z")
        assert client.get(response.headers["location"], headers=AUTH).json() == body


def test_sync_deadline_is_not_success_and_replay_is_same_job(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        headers = {**AUTH, "Idempotency-Key": "same"}
        response = client.post("/v1/google-flow/videos", headers=headers, json={"prompt": "x"})
        assert response.status_code == 408
        body = response.json()
        assert body["processingContinues"] is True and body["retryable"] is False
        retry = client.post(
            "/v1/google-flow/videos", headers=headers, json={"prompt": "x", "async": True}
        )
        assert retry.status_code == 201
        assert retry.json()["jobId"] == body["jobId"]
        assert len(client.app.state.store.jobs()) == 1


@pytest.mark.parametrize("exit_code,status", [(10, 403), (37, 402), (3, 596), (4, 429), (1, 502)])
def test_sync_typed_failure_never_200(tmp_path, exit_code, status):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        headers = {**AUTH, "Idempotency-Key": "failed"}
        response = client.post(
            "/v1/google-flow/videos", headers=headers, json={"prompt": "x", "async": True}
        )
        job = response.json()["jobId"]
        client.app.state.store.finish(
            job,
            "failed",
            {
                "error": {
                    "code": "gflow_command_failed",
                    "exit_code": exit_code,
                    "retryable": False,
                    "detail": "do not echo secret absolute path /private/token",
                }
            },
        )
        result = client.post("/v1/google-flow/videos", headers=headers, json={"prompt": "x"})
        assert result.status_code == status
        assert isinstance(result.json()["error"], str)
        assert "/private/token" not in result.text


def test_callback_record_matches_polling_and_redacts_internal_fields(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={
                "prompt": "x",
                "async": True,
                "replyRef": "r",
                "replyUrl": "https://callbacks.example/hook",
            },
        )
        identifier = response.json()["jobId"]
        store.claim("pro1")
        store.finish(
            identifier,
            "interrupted",
            {
                "knownMediaGenerationIds": [PROJECT],
                "error": {"code": "submission_outcome_unknown", "retryable": False},
                "internalPath": "/private/token",
                "captchaToken": "SECRET",
            },
        )
        record = client.get(f"/v1/google-flow/jobs/{identifier}", headers=AUTH).json()
        assert record["status"] == "failed" and record["outcomeUnknown"] is True
        assert record["knownMediaGenerationIds"] == [PROJECT]
        with store.connection() as connection:
            callback = json.loads(
                connection.execute(
                    "SELECT payload FROM callbacks WHERE job=? AND state='interrupted'",
                    (identifier,),
                ).fetchone()[0]
            )
        assert callback == record
        assert "/private/token" not in json.dumps(record) and "SECRET" not in json.dumps(record)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1, 901])
def test_invalid_wait_is_rejected_before_start(tmp_path, value):
    with pytest.raises(ValueError, match="Sync wait"):
        Settings(token="test", root=tmp_path, accounts={}, sync_wait=value)


@pytest.mark.parametrize("value", [False, None, {}, ["r"], "r" * 4097])
def test_invalid_reply_ref_does_not_enqueue(tmp_path, value):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        result = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "x", "async": True, "replyRef": value},
        )
        assert result.status_code == 422
        assert client.app.state.store.jobs() == []


def test_started_and_unknown_failure_filters_match_projected_states(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        job = store.submit("images", "pro1", {"prompt": "legacy"}, None)
        store.claim("pro1")
        started = client.get("/v1/google-flow/jobs?status=started", headers=AUTH).json()
        assert started["jobs"][0]["status"] == "started"
        assert started["jobs"][0]["jobid"] == job["jobId"]
        type(store)(tmp_path).recover()
        failed = client.get("/v1/google-flow/jobs?status=failed", headers=AUTH).json()
        assert failed["jobs"][0]["outcomeUnknown"] is True
        assert store.claim("pro1") is None


def test_nested_projection_excludes_secrets_and_absolute_paths(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        job = store.submit(
            "images",
            "pro1",
            {
                "prompt": "x",
                "captchaToken": "SECRET",
                "captchaSecret": "/private/token",
                "refPaths": ["/private/image"],
                "unknown": {"token": "SECRET"},
            },
            None,
        )
        store.finish(
            job["jobId"],
            "completed",
            {
                "media": [
                    {
                        "mediaGenerationId": PROJECT,
                        "local_path": "/private/image",
                        "image": {
                            "captchaToken": "SECRET",
                            "downloadPath": "/private/image",
                            "generatedImage": {
                                "encodedImage": "aGk=",
                                "seed": 42,
                                "token": "SECRET",
                                "fifeUrl": "https://signed/?token=x",
                            },
                        },
                    }
                ],
                "captchaToken": "SECRET",
            },
        )
        body = store.get_record(job["jobId"])
        assert body["response"]["media"][0]["image"]["generatedImage"] == {
            "encodedImage": "aGk=",
            "seed": 42,
        }
        assert "SECRET" not in json.dumps(body) and "/private" not in json.dumps(body)
        assert "media" not in body  # Never duplicate the large encoded payload.


def test_callback_snapshot_equality_for_every_transition(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        job = store.submit(
            "images",
            "pro1",
            {"replyUrl": "https://callbacks.example/hook", "replyRef": "client"},
            None,
        )

        def assert_latest():
            with store.connection() as connection:
                payload = connection.execute(
                    "SELECT payload FROM callbacks WHERE job=? ORDER BY id DESC LIMIT 1",
                    (job["jobId"],),
                ).fetchone()[0]
            assert json.loads(payload) == store.get_record(job["jobId"])

        assert_latest()
        store.claim("pro1")
        assert_latest()
        store.finish(job["jobId"], "completed", {"media": []})
        assert_latest()


def test_upload_and_archive_public_results_keep_safe_contract(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        job = store.submit("assets", "pro1", {"input": "/private/image", "mime": "image/png"}, None)
        store.finish(
            job["jobId"], "completed", {"mediaGenerationId": {"mediaGenerationId": PROJECT}}
        )
        assert store.get_record(job["jobId"])["response"]["mediaGenerationId"] == {
            "mediaGenerationId": PROJECT
        }
        assert "/private" not in json.dumps(store.get_record(job["jobId"]))
        archived = store.submit("assets/archive", "pro1", {"mediaGenerationIds": [PROJECT]}, None)
        store.finish(
            archived["jobId"],
            "completed",
            {
                "deleted": [PROJECT],
                "operation": "archive",
                "googleLibraryModified": True,
                "localCacheModified": False,
                "scope": "google-project-library",
            },
        )
        assert store.get_record(archived["jobId"])["response"]["deleted"] == [PROJECT]
        assert store.get_record(archived["jobId"])["response"]["googleLibraryModified"] is True


def test_pending_legacy_callback_migration_preserves_snapshot_state(tmp_path):
    from gflow_cli.selfhost.store import Store

    store = Store(tmp_path)
    job = store.submit("images", "pro1", {"replyUrl": "https://callbacks.example/hook"}, None)
    store.claim("pro1")
    store.finish(job["jobId"], "completed", {"media": []})
    with store.connection() as connection:
        connection.execute(
            "UPDATE callbacks SET payload=? WHERE job=? AND state='created'",
            (
                json.dumps(
                    {
                        "jobId": job["jobId"],
                        "status": "created",
                        "createdAt": 10,
                        "updatedAt": 10,
                        "captchaToken": "SECRET",
                    }
                ),
                job["jobId"],
            ),
        )
    upgraded = Store(tmp_path)
    with upgraded.connection() as connection:
        body = json.loads(
            connection.execute(
                "SELECT payload FROM callbacks WHERE job=? AND state='created'", (job["jobId"],)
            ).fetchone()[0]
        )
    assert body["status"] == "created" and body["createdAt"] == body["updatedAt"] == 10
    assert "SECRET" not in json.dumps(body)
    assert upgraded.get(job["jobId"])["status"] == "completed"


def test_confirmed_delete_metadata_survives_public_and_repeated_projection(tmp_path):
    from gflow_cli.selfhost.http_jobs import result_record

    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        store = client.app.state.store
        job = store.submit("assets/delete", "pro1", {"mediaGenerationIds": [PROJECT]}, None)
        response = {
            "projectId": PROJECT,
            "operation": "delete",
            "deleted": [PROJECT],
            "deletedCount": 1,
            "newlyDeleted": [],
            "alreadyDeleted": [PROJECT],
            "receiptPersisted": True,
            "googleLibraryModified": False,
            "localCacheModified": False,
        }
        store.finish(job["jobId"], "completed", response)
        body = client.get("/v1/google-flow/jobs/" + job["jobId"], headers=AUTH).json()
        public = body["response"]
        for key in ("deletedCount", "newlyDeleted", "alreadyDeleted", "receiptPersisted"):
            assert public[key] == response[key]
            assert result_record(public)[key] == response[key]
        assert public["googleLibraryModified"] is False


@pytest.mark.parametrize(
    "override",
    [
        {"deletedCount": True},
        {"deletedCount": 2},
        {"receiptPersisted": "true"},
        {"newlyDeleted": [PROJECT], "alreadyDeleted": [PROJECT]},
        {"alreadyDeleted": ["/private/path"]},
        {"alreadyDeleted": []},
    ],
)
def test_malformed_delete_retry_metadata_is_not_published(override):
    from gflow_cli.selfhost.http_jobs import result_record

    response = {
        "projectId": PROJECT,
        "operation": "delete",
        "deleted": [PROJECT],
        "deletedCount": 1,
        "newlyDeleted": [],
        "alreadyDeleted": [PROJECT],
        "receiptPersisted": True,
        **override,
    }
    result = result_record(response, kind="assets/delete")
    assert "deletedCount" not in result and "receiptPersisted" not in result


def test_native_delete_defaults_to_selected_account_project(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.request(
            "DELETE",
            "/v1/google-flow/assets/fixture",
            headers=AUTH,
            json={
                "mediaGenerationIds": ["22222222-2222-4222-8222-222222222222"],
                "operation": "delete",
                "async": True,
            },
        )
        assert response.status_code == 201
        row = client.app.state.store.get_record(response.json()["jobId"])
        assert row["request"]["projectId"] == PROJECT
        assert response.json()["request"]["projectId"] == PROJECT


@pytest.mark.parametrize("project", [None, "bad", True])
def test_explicit_invalid_delete_project_does_not_use_default(tmp_path, project):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.request(
            "DELETE",
            "/v1/google-flow/assets/fixture",
            headers=AUTH,
            json={
                "mediaGenerationIds": ["22222222-2222-4222-8222-222222222222"],
                "operation": "delete",
                "projectId": project,
                "async": True,
            },
        )
        assert response.status_code == 422
        assert not client.app.state.store.jobs()


def test_native_delete_default_project_is_scoped_to_selected_account(tmp_path):
    settings = cfg(tmp_path)
    other_project = "33333333-3333-4333-8333-333333333333"
    settings.accounts["pro2"] = {"email": "second-fixture", "project": other_project}
    with TestClient(create_app(settings, start_workers=False)) as client:
        response = client.request(
            "DELETE",
            "/v1/google-flow/assets/second-fixture",
            headers=AUTH,
            json={
                "mediaGenerationIds": ["22222222-2222-4222-8222-222222222222"],
                "operation": "delete",
                "async": True,
            },
        )
        assert response.status_code == 201
        row = client.app.state.store.get_record(response.json()["jobId"])
        assert row["request"]["projectId"] == other_project
        assert row["request"]["projectId"] != PROJECT


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("nano-banana", "nano-banana-2"), ("imagen-4", "nano-banana-2-lite")],
)
def test_useapi_deprecated_image_aliases_normalize_before_enqueue(tmp_path, alias, canonical):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={
                "prompt": "A small blue ceramic vase.",
                "model": alias,
                "count": 1,
                "async": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["request"]["model"] == canonical
        record = client.app.state.store.get_record(response.json()["jobId"])
        assert record["request"]["model"] == canonical


@pytest.mark.parametrize(("alias", "ratio"), [("landscape", "16:9"), ("portrait", "9:16")])
def test_useapi_image_aspect_aliases_normalize_before_enqueue(tmp_path, alias, ratio):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "A ceramic vase.", "aspectRatio": alias, "count": 1, "async": True},
        )
        assert response.status_code == 201
        assert response.json()["request"]["aspectRatio"] == ratio


def test_useapi_uppercase_4k_normalizes_for_explicit_native_promotion(tmp_path):
    with TestClient(create_app(cfg(tmp_path), start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/videos/upscale",
            headers=AUTH,
            json={
                "mediaGenerationId": "22222222-2222-4222-8222-222222222222",
                "operation": "promotion",
                "resolution": "4K",
                "async": True,
            },
        )
        assert response.status_code == 201
        assert response.json()["request"]["resolution"] == "4k"
