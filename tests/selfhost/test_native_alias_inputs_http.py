"""Generation aliases resolve exact scoped bindings before fresh proof and queueing."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore
from gflow_cli.selfhost.native_resource_aliases import NativeResourceAlias, NativeResourceAliasStore
from gflow_cli.selfhost.server import Settings, create_app

P = "11111111-1111-4111-8111-111111111111"
Q = "22222222-2222-4222-8222-222222222222"
R = "33333333-3333-4333-8333-333333333333"
M = "44444444-4444-4444-8444-444444444444"
V = "55555555-5555-4555-8555-555555555555"
C = "66666666-6666-4666-8666-666666666666"
A = "77777777-7777-4777-8777-777777777777"
VW = "88888888-8888-4888-8888-888888888888"
W = "99999999-9999-4999-8999-999999999999"
M2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
IMAGE = "user:fixture-email:opaque-image:" + M
IMAGE2 = "user:fixture-email:opaque-image:" + M2
VIDEO = "user:fixture-email:opaque-video:" + V
CHARACTER = "user:fixture-email:opaque-character:" + C + "-imgs:1"
VOICE = "user:fixture-email:opaque-voice:" + VW + "-mid:" + A
FOREIGN = "user:other-email:opaque-image:" + M
AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []
    state = {"stale": False, "image_count": 1}

    async def run(argv, timeout):
        calls.append(argv)
        query = json.loads(argv[5])
        project = query["project_id"]
        if state["stale"]:
            return 1, b"{}"
        if argv[3] == "asset-cache-image":
            output_dir = Path(query["output_dir"])
            assert output_dir.is_relative_to(tmp_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "cached.png"
            Image.new("RGB", (8, 8)).save(path)
            result = {
                "status": "ok",
                "mediaGenerationId": query["media_id"],
                "projectId": project,
                "kind": "image",
                "path": str(path),
                "mimeType": "image/png",
                "bytes": path.stat().st_size,
            }
            fault = state.get("cache_fault")
            if fault == "escape":
                result["path"] = str(tmp_path.parent / "outside.png")
            elif fault == "kind":
                result["kind"] = "video"
            elif fault == "mime":
                result["mimeType"] = "video/mp4"
            elif fault == "over-budget":
                result["bytes"] = 20 * 1024 * 1024 + 1
            elif fault == "media":
                result["mediaGenerationId"] = M2
            elif fault == "project":
                result["projectId"] = R
            elif fault == "bytecount":
                result["bytes"] += 1
            return 0, json.dumps(result).encode()
        if argv[3] == "asset-get":
            media = query["media_id"]
            kind = "video" if media == V else "image"
            return 0, json.dumps(
                {
                    "status": "ok",
                    "mediaGenerationId": media,
                    "projectId": project,
                    "kind": kind,
                    "url": "https://flow-content.google/" + kind + "/fixture",
                    "width": 1280,
                    "height": 720,
                }
            ).encode()
        if argv[3] == "character-detail":
            refs = [
                {"media_id": value, "workflow_id": W} for value in (M, M2)[: state["image_count"]]
            ]
            return 0, json.dumps(
                {
                    "status": "ok",
                    "project_id": project,
                    "character": {
                        "project_id": project,
                        "entity_id": query["entity_id"],
                        "image_references": refs,
                    },
                }
            ).encode()
        if argv[3] == "voice-saved-get":
            return 0, json.dumps(
                {
                    "status": "ok",
                    "project_id": project,
                    "ref": query["ref"],
                    "voice": query["ref"],
                    "workflow_id": VW,
                    "source": "user",
                    "audio_url": "https://flow-content.google/audio/fixture",
                }
            ).encode()
        pytest.fail("Unexpected worker dispatch")

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test",
        root=tmp_path,
        accounts={"pro1": {"email": "one", "project": P}, "pro2": {"email": "two", "project": R}},
        callbacks=(),
        sync_wait=0,
        allow_video=True,
    )
    aliases = NativeAliasStore(tmp_path)
    aliases.register(NativeAlias(IMAGE, "pro1", "one", Q, M, "image"))
    aliases.register(NativeAlias(IMAGE2, "pro1", "one", Q, M2, "image"))
    aliases.register(NativeAlias(VIDEO, "pro1", "one", Q, V, "video"))
    aliases.register(NativeAlias(FOREIGN, "pro2", "two", R, M, "image"))
    resources = NativeResourceAliasStore(tmp_path)
    resources.register(
        NativeResourceAlias(CHARACTER, "pro1", "one", Q, "character", C, image_count=1)
    )
    resources.register(NativeResourceAlias(VOICE, "pro1", "one", Q, "voice", A, workflow_id=VW))
    with TestClient(create_app(cfg, start_workers=False)) as client:
        for identifier in (M, M2):
            path = tmp_path / (identifier + ".png")
            Image.new("RGB", (8, 8)).save(path)
            client.app.state.store.asset(identifier, "pro1", Q, str(path), "image/png")
        yield client, calls, state


def post(client, route, payload):
    return client.post("/v1/google-flow/" + route, headers=AUTH, json={"async": True, **payload})


def claim(client):
    row = client.app.state.store.claim("pro1")
    assert row is not None
    return json.loads(row["payload"])


def no_jobs(client):
    assert client.app.state.store.job_page(limit=100)["jobs"] == []


def test_image_aliases_derive_nondefault_project_and_preserve_slots(api):
    client, calls, state = api
    response = post(
        client,
        "images",
        {
            "prompt": "@reference_3 @character_2",
            "model": "nano-banana-2",
            "count": 1,
            "aspectRatio": "1:1",
            "reference_3": IMAGE,
            "character_2": CHARACTER,
        },
    )
    assert response.status_code == 201, response.text
    payload = claim(client)
    assert payload["email"] == "one" and payload["projectId"] == Q
    assert payload["reference_3"] == M and payload["character_2"] == C
    assert payload["reference_prompt_plan"]["image_ids"] == [M]
    assert payload["reference_prompt_plan"]["character_ids"] == [C]
    assert [
        span["slot"] for span in payload["reference_prompt_plan"]["spans"] if "slot" in span
    ] == ["reference_3", "character_2"]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "route,extra",
    [
        ("images/upscale", {"mediaGenerationId": IMAGE}),
        ("videos/extend", {"mediaGenerationId": VIDEO, "prompt": "Continue slowly"}),
        (
            "videos/upscale",
            {"mediaGenerationId": VIDEO, "operation": "promotion", "resolution": "720p"},
        ),
        ("videos/gif", {"mediaGenerationId": VIDEO, "resolution": "270p"}),
    ],
)
def test_single_media_alias_operation_forwarding(api, route, extra):
    client, calls, state = api
    response = post(client, route, extra)
    assert response.status_code == 201, response.text
    payload = claim(client)
    assert payload["projectId"] == Q and payload["email"] == "one"
    assert payload["mediaGenerationId"] == (M if route.startswith("images") else V)
    assert len(calls) == 1


@pytest.mark.parametrize("editing", [False, True])
def test_native_video_aliases_preserve_mixed_slots_and_presets(api, editing):
    client, calls, state = api
    payload = {
        "prompt": "@referenceImage_3 @character_2 @referenceAudio_1",
        "model": "omni-flash",
        "count": 1,
        "referenceImage_3": IMAGE,
        "character_2": CHARACTER,
        "referenceAudio_1": VOICE,
        "referenceAudio_2": "Charon",
    }
    if editing:
        payload.update(
            referenceVideo_1=VIDEO,
            modelKey="validation-native-model",
            startFrameIndex_1=0,
            endFrameIndex_1=192,
        )
    response = post(client, "videos", payload)
    assert response.status_code == 201, response.text
    result = claim(client)
    assert result["projectId"] == Q and result["email"] == "one"
    assert result["referenceImage_3"] == M and result["character_2"] == C
    assert result["referenceAudio_1"] == A and result["referenceAudio_2"] == "Charon"
    assert result["referenceSlotIds"]["referenceImage_3"] == M
    assert result["referenceSlotIds"]["character_2"] == C
    if editing:
        assert result["referenceVideo_1"] == V
    assert len(calls) == (4 if editing else 3)


def test_general_video_frame_aliases_forward_managed_uuid_sources(api):
    client, calls, state = api
    response = post(
        client,
        "videos",
        {"prompt": "A calm scene", "startImage": IMAGE, "endImage": IMAGE2, "count": 1},
    )
    assert response.status_code == 201, response.text
    result = claim(client)
    assert result["projectId"] == Q and result["startImage"] == M and result["endImage"] == M2
    assert not any(call[3] == "asset-cache-image" for call in calls)


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"reference_1": IMAGE.replace("user:fixture", "user:unknown")}, 404),
        ({"email": "two"}, 403),
        ({"projectId": P}, 403),
        ({"reference_2": FOREIGN}, 409),
        ({"reference_1": VIDEO}, 400),
    ],
)
def test_invalid_alias_sets_refuse_before_fresh_reads_or_queue(api, changes, status):
    client, calls, state = api
    response = post(
        client, "images", {"prompt": "A small scene", "reference_1": IMAGE, "count": 1, **changes}
    )
    assert response.status_code == status, response.text
    assert calls == []
    no_jobs(client)


def test_disabled_alias_account_refuses_before_read_and_queue(api):
    client, calls, state = api
    client.app.state.store.account_set("pro1", "one", P, enabled=False, verified=True)
    response = post(client, "images", {"prompt": "A small scene", "reference_1": IMAGE, "count": 1})
    assert response.status_code == 403, response.text
    assert calls == []
    no_jobs(client)


@pytest.mark.parametrize("change", ["stale", "count"])
def test_stale_fresh_detail_or_changed_character_count_refuses_queue(api, change):
    client, calls, state = api
    state["stale"] = change == "stale"
    state["image_count"] = 2 if change == "count" else 1
    response = post(
        client, "images", {"prompt": "@character_1", "character_1": CHARACTER, "count": 1}
    )
    assert response.status_code == 502, response.text
    no_jobs(client)


def test_native_video_duplicate_alias_and_uuid_refused(api):
    client, calls, state = api
    response = post(
        client,
        "videos",
        {
            "prompt": "A calm scene",
            "model": "omni-flash",
            "referenceImage_1": IMAGE,
            "referenceImage_2": M,
            "count": 1,
        },
    )
    assert response.status_code == 422, response.text
    no_jobs(client)


def test_image_alias_and_raw_uuid_deduplicate_source_but_preserve_both_slots(api):
    client, calls, state = api
    response = post(
        client,
        "images",
        {
            "prompt": "@reference_1 then @reference_2",
            "model": "nano-banana-2",
            "reference_1": IMAGE,
            "reference_2": M,
            "aspectRatio": "1:1",
            "count": 1,
        },
    )
    assert response.status_code == 201, response.text
    payload = claim(client)
    assert payload["reference_prompt_plan"]["image_ids"] == [M]
    assert payload["reference_1"] == payload["reference_2"] == M
    assert [
        span["slot"] for span in payload["reference_prompt_plan"]["spans"] if "slot" in span
    ] == ["reference_1", "reference_2"]
    assert len(payload["_image_reference_sources"]) == 1


@pytest.mark.parametrize("editing", [False, True])
def test_native_video_highest_supported_slot_indices_survive_translation(api, editing):
    client, calls, state = api
    image_key = "referenceImage_5" if editing else "referenceImage_7"
    audio_key = "referenceAudio_3" if editing else "referenceAudio_5"
    payload = {
        "prompt": "A calm scene",
        "model": "omni-flash",
        "count": 1,
        image_key: IMAGE,
        audio_key: VOICE,
        "character_7": CHARACTER,
    }
    if editing:
        payload.update(
            referenceVideo_1=VIDEO,
            modelKey="validation-native-model",
            startFrameIndex_1=0,
            endFrameIndex_1=192,
        )
    response = post(client, "videos", payload)
    assert response.status_code == 201, response.text
    result = claim(client)
    assert result[image_key] == M and result[audio_key] == A
    assert result["character_7"] == C
    assert result["referenceSlotIds"][image_key] == M
    assert result["referenceSlotIds"][audio_key] == A


def test_late_unknown_reference_refuses_entire_batch_before_fresh_reads(api):
    client, calls, state = api
    response = post(
        client,
        "images",
        {
            "prompt": "A small scene",
            "reference_1": IMAGE,
            "character_1": CHARACTER,
            "reference_10": IMAGE2.replace("user:fixture", "user:unknown"),
            "count": 1,
        },
    )
    assert response.status_code == 404
    assert calls == []
    no_jobs(client)


@pytest.mark.parametrize("editing", [False, True])
def test_character_alias_in_mixed_video_image_slot_keeps_original_slot(api, editing):
    client, calls, state = api
    payload = {
        "prompt": "@referenceImage_3 in a calm scene",
        "model": "omni-flash",
        "count": 1,
        "referenceImage_3": CHARACTER,
    }
    if editing:
        payload.update(
            referenceVideo_1=VIDEO,
            modelKey="validation-native-model",
            startFrameIndex_1=0,
            endFrameIndex_1=192,
        )
    response = post(client, "videos", payload)
    assert response.status_code == 201, response.text
    result = claim(client)
    assert result["referenceImage_3"] == C
    assert result["referenceSlotIds"]["referenceImage_3"] == C
    assert "character_1" not in result


def test_uncached_general_video_alias_downloads_owned_image_before_queue(api):
    client, calls, state = api
    client.app.state.store.asset_delete(M)
    response = post(client, "videos", {"prompt": "A calm scene", "startImage": IMAGE, "count": 1})
    assert response.status_code == 201, response.text
    result = claim(client)
    assert result["startImage"] == M
    assert result["email"] == "one" and result["projectId"] == Q
    row = client.app.state.store.asset_get(M)
    assert row["profile"] == "pro1" and row["project"] == Q and row["mime"] == "image/png"
    cached = Path(row["path"])
    assert cached.is_file()
    assert [call[3] for call in calls] == ["asset-get", "asset-cache-image"]
    assert json.loads(calls[-1][5])["project_id"] == Q


@pytest.mark.parametrize(
    "fault", ["escape", "kind", "mime", "over-budget", "media", "project", "bytecount"]
)
def test_uncached_alias_rejects_invalid_private_download_without_queue(api, fault):
    client, calls, state = api
    client.app.state.store.asset_delete(M)
    state["cache_fault"] = fault
    response = post(client, "videos", {"prompt": "A calm scene", "startImage": IMAGE, "count": 1})
    assert response.status_code == 502, response.text
    no_jobs(client)
    with pytest.raises(KeyError):
        client.app.state.store.asset_get(M)
    assert [call[3] for call in calls] == ["asset-get", "asset-cache-image"]


def test_general_video_alias_does_not_override_foreign_managed_asset(api):
    client, calls, state = api
    store = client.app.state.store
    original = store.asset_get(M)
    store.asset(M, "pro2", R, original["path"], original["mime"])
    before = store.asset_get(M)
    response = post(client, "videos", {"prompt": "A calm scene", "startImage": IMAGE, "count": 1})
    assert response.status_code == 422, response.text
    no_jobs(client)
    assert store.asset_get(M) == before
    assert not any(call[3] == "asset-cache-image" for call in calls)
