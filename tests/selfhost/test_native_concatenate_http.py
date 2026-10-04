"""Native alias/UUID concatenation preflight with real local MP4 bytes, no Google."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore
from gflow_cli.selfhost.server import Settings, create_app
from tests.selfhost.test_concatenate import real_clips as _real_clips

real_clips = _real_clips

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
R = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
N = "55555555-5555-4555-8555-555555555555"
A = "user:opaque-email:hidden-video:" + M
B = "user:opaque-email:hidden-video:" + N
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch, real_clips):
    calls = []
    state = {}

    async def run(argv, timeout):
        verb = argv[3]
        query = json.loads(argv[5])
        calls.append((verb, query))
        if verb == "asset-get":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "mediaGenerationId": query["media_id"],
                    "projectId": query["project_id"],
                    "kind": "image" if state.get("wrongkind") else "video",
                    "url": "https://flow-content.google/video/fixture",
                    "width": 64,
                    "height": 64,
                }
            ).encode()
        assert verb == "asset-download"
        directory = Path(query["output_dir"])
        path = directory / "video.mp4"
        shutil.copyfile(real_clips[0 if query["media_id"] == M else 1].path, path)
        result = {
            "status": "ok",
            "mediaGenerationId": query["media_id"],
            "projectId": query["project_id"],
            "kind": "video",
            "path": str(path),
            "mimeType": "video/mp4",
            "bytes": path.stat().st_size,
        }
        fault = state.get("fault")
        if fault == "escape":
            result["path"] = str(real_clips[0].path)
        elif fault == "mime":
            result["mimeType"] = "image/png"
        elif fault == "id":
            result["mediaGenerationId"] = R
        elif fault == "project":
            result["projectId"] = R
        elif fault == "bytes":
            result["bytes"] += 1
        elif fault == "oversize":
            result["bytes"] = 256 * 1024 * 1024 + 1
        elif fault == "decode":
            path.write_bytes(b"xxxxftypxxxx")
            result["bytes"] = 12
        return 0, json.dumps(result).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "one", "project": P}, "pro2": {"email": "two", "project": R}},
        callbacks=(),
        sync_wait=0,
    )
    state["cfg"] = cfg
    aliases = NativeAliasStore(tmp_path)
    aliases.register(NativeAlias(A, "pro1", "one", Q, M, "video"))
    aliases.register(NativeAlias(B, "pro1", "one", Q, N, "video"))
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls, state


def post(client, media, **fields):
    return client.post(
        "/v1/google-flow/videos/concatenate",
        headers=AUTH,
        json={"media": [{"mediaGenerationId": ref} for ref in media], "async": True, **fields},
    )


def jobs(client):
    return client.get("/v1/google-flow/jobs?source=local", headers=AUTH).json()["jobs"]


def test_alias_inputs_derive_exact_scope_cache_order_and_private_payload(api):
    client, calls, _ = api
    response = post(client, [B, A])
    assert response.status_code == 201, response.text
    job = client.app.state.store.claim("pro1")
    payload = json.loads(job["payload"])
    assert payload["project"] == Q and payload["email"] == "one"
    assert [item["mediaGenerationId"] for item in payload["media"]] == [N, M]
    assert "https:" not in job["payload"] and "user:" not in job["payload"]
    assert [verb for verb, _ in calls] == [
        "asset-get",
        "asset-get",
        "asset-download",
        "asset-download",
    ]
    for identifier in (M, N):
        row = client.app.state.store.asset_get(identifier)
        path = Path(row["path"])
        assert row["project"] == Q and path.stat().st_mode & 0o777 == 0o600


def test_raw_native_uuid_with_explicit_scope(api):
    client, calls, _ = api
    response = post(client, [M, N], email="one", projectId=Q)
    assert response.status_code == 201, response.text
    assert [verb for verb, _ in calls].count("asset-get") == 2


def test_duplicate_alias_slots_download_once_and_reverify_cached(api):
    client, calls, _ = api
    assert post(client, [A, A]).status_code == 201
    assert [verb for verb, _ in calls] == ["asset-get", "asset-download"]
    calls.clear()
    assert post(client, [M, M], email="one", projectId=Q).status_code == 201
    assert [verb for verb, _ in calls] == ["asset-get"]
    assert len(jobs(client)) == 2


@pytest.mark.parametrize(
    "case", ["unknown", "foreign-email", "foreign-project", "mixed", "wrongkind"]
)
def test_invalid_native_batch_no_download_or_queue(api, case, tmp_path):
    client, calls, state = api
    fields = {}
    refs = [A, B]
    if case == "unknown":
        refs = ["user:other-email:hidden-video:" + M, B]
    elif case == "foreign-email":
        fields["email"] = "two"
    elif case == "foreign-project":
        fields["projectId"] = R
    elif case == "mixed":
        NativeAliasStore(tmp_path).register(
            NativeAlias("user:foreign-email:hidden-video:" + M, "pro2", "two", R, M, "video")
        )
        refs[0] = "user:foreign-email:hidden-video:" + M
    else:
        state["wrongkind"] = True
    response = post(client, refs, **fields)
    assert response.status_code in (400, 403, 404, 409, 502), response.text
    assert not any(verb == "asset-download" for verb, _ in calls)
    assert jobs(client) == []


@pytest.mark.parametrize(
    "fault", ["escape", "mime", "id", "project", "bytes", "oversize", "decode"]
)
def test_invalid_private_download_no_queue_and_partial_cleanup(api, fault):
    client, calls, state = api
    state["fault"] = fault
    response = post(client, [A, B])
    assert response.status_code == 502, response.text
    assert jobs(client) == []
    assert not list(client.app.state.store.root.glob("native-video-cache/*/*/*/video.mp4"))


def test_foreign_global_cache_conflict_refuses_before_reads(api, tmp_path):
    client, calls, _ = api
    path = tmp_path / "foreign.mp4"
    path.write_bytes(b"foreign")
    client.app.state.store.asset(M, "pro2", R, str(path), "video/mp4")
    response = post(client, [A, B])
    assert response.status_code == 422
    assert calls == [] and jobs(client) == []
    assert client.app.state.store.asset_get(M)["profile"] == "pro2"


@pytest.mark.asyncio
async def test_native_inputs_cache_to_actual_local_ffmpeg_output(api):
    from gflow_cli.selfhost.concatenate import probe
    from gflow_cli.selfhost.runtime import execute

    client, calls, state = api
    response = post(client, [A, B])
    assert response.status_code == 201
    store = client.app.state.store
    job = store.claim("pro1")
    result = await execute(state["cfg"], store, job)
    assert result["backend"] == "local-ffmpeg"
    assert result["inputsCount"] == 2
    assert "mediaGenerationId" not in result
    row = store.asset_get(result["localArtifactId"])
    output = Path(row["path"])
    info = await probe(output)
    assert info.duration == pytest.approx(4, abs=0.15)
    assert info.width == 64 and info.height == 64 and info.has_audio
    assert len(calls) == 4
    store.finish(job["id"], "completed", result)
    public = client.get("/v1/google-flow/jobs/" + job["id"], headers=AUTH).json()
    assert public["inputsCount"] == 2
    assert public["response"]["inputsCount"] == 2


@pytest.mark.parametrize("value", [True, False, 0, 1, 11, "2", 2.0, None])
def test_invalid_inputs_count_is_not_public(value):
    from gflow_cli.selfhost.http_jobs import result_record

    assert "inputsCount" not in result_record({"inputsCount": value}, kind="videos/concatenate")


def test_inputs_count_only_public_for_concatenation():
    from gflow_cli.selfhost.http_jobs import result_record

    assert result_record({"inputsCount": 2}, kind="videos/concatenate")["inputsCount"] == 2
    assert "inputsCount" not in result_record({"inputsCount": 2}, kind="videos")
