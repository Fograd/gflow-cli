"""UseAPI defaults select telemetry and combined fresh voice inventories."""

import pytest
from fastapi.testclient import TestClient

from tests.selfhost.test_job_statistics import AUTH, app, insert


def test_jobs_without_query_defaults_to_official_summary(tmp_path):
    with TestClient(app(tmp_path)) as client:
        insert(client.app.state.store, "one", "images", "completed")
        value = client.get("/v1/google-flow/jobs", headers=AUTH).json()
        assert value["images"]["summary"]["account-one"]["completed"] == 1
        assert "jobs" not in value


def test_jobs_explicit_local_source_retains_durable_list(tmp_path):
    with TestClient(app(tmp_path)) as client:
        identifier = insert(client.app.state.store, "one", "images", "completed")
        response = client.get("/v1/google-flow/jobs?source=local", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["jobs"][0]["jobId"] == identifier


def test_jobs_explicit_list_filters_remain_compatible(tmp_path):
    with TestClient(app(tmp_path)) as client:
        insert(client.app.state.store, "one", "images", "completed")
        response = client.get("/v1/google-flow/jobs?limit=1", headers=AUTH)
        assert response.status_code == 200 and len(response.json()["jobs"]) == 1


def test_jobs_rejects_local_statistics_mix_and_unknown_source(tmp_path):
    with TestClient(app(tmp_path)) as client:
        for query in ("source=local&options=summary", "source=unknown"):
            assert client.get("/v1/google-flow/jobs?" + query, headers=AUTH).status_code == 400


@pytest.fixture
def voice_api(tmp_path, monkeypatch):
    import json

    from gflow_cli.selfhost.server import Settings, create_app

    calls = []

    async def run(argv, timeout):
        calls.append((argv[3], argv[4], json.loads(argv[5])))
        if argv[3] == "voice-presets":
            rows = [
                {
                    "voice": "Charon",
                    "description": "Informative",
                    "sample_url": "https://www.gstatic.com/aitestkitchen/voices/samples/Charon.wav",
                }
            ]
        elif argv[3] == "voice-saved-list":
            rows = [
                {
                    "ref": "33333333-3333-4333-8333-333333333333",
                    "project_id": "11111111-1111-4111-8111-111111111111",
                    "workflow_id": "44444444-4444-4444-8444-444444444444",
                    "display_name": "Fixture",
                    "preset_voice": "Charon",
                    "audio_url": "https://flow-content.google/audio/private",
                }
            ]
        else:
            pytest.fail("Unexpected worker dispatch")
        return 0, json.dumps({"status": "ok", "voices": rows}).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    cfg = Settings(
        token="test-token",
        root=tmp_path,
        accounts={
            "one": {"email": "account-one", "project": "11111111-1111-4111-8111-111111111111"}
        },
    )
    with TestClient(create_app(cfg, start_workers=False)) as client:
        yield client, calls


def test_default_voice_list_reads_both_fresh_catalogs_metadata_only(voice_api):
    client, calls = voice_api
    response = client.get("/v1/google-flow/voices?email=account-one", headers=AUTH)
    assert response.status_code == 200, response.text
    voices = response.json()["voices"]
    assert [row["source"] for row in voices] == ["system", "user"]
    assert voices[0]["voice"] == "Charon"
    assert "audioUrl" not in voices[1]
    assert [row[0] for row in calls] == ["voice-presets", "voice-saved-list"]
    assert all(
        row[1] == "one" and row[2]["project_id"] == "11111111-1111-4111-8111-111111111111"
        for row in calls
    )


def test_default_voice_list_requires_selected_account(voice_api):
    client, calls = voice_api
    response = client.get("/v1/google-flow/voices", headers=AUTH)
    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    "query,expected",
    [
        ("email=account-one&source=user", ["voice-saved-list"]),
        ("email=account-one&source=system&catalog=google", ["voice-presets"]),
        ("source=system&catalog=bundled", []),
        ("catalog=bundled", []),
    ],
)
def test_explicit_voice_catalog_extensions_keep_prior_scope(voice_api, query, expected):
    client, calls = voice_api
    response = client.get("/v1/google-flow/voices?" + query, headers=AUTH)
    assert response.status_code == 200, response.text
    assert [row[0] for row in calls] == expected


def test_system_voice_singleton_still_works_without_account(voice_api):
    client, calls = voice_api
    response = client.get("/v1/google-flow/voices/charon", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["source"] == "system"
    assert calls == []


def test_combined_voice_inventory_freezes_scope_and_refuses_account_changes(tmp_path, monkeypatch):
    import json

    from gflow_cli.selfhost.server import Settings, create_app

    project = "11111111-1111-4111-8111-111111111111"
    changed_project = "22222222-2222-4222-8222-222222222222"
    cfg = Settings(
        token="test-token",
        root=tmp_path,
        accounts={"one": {"email": "account-one", "project": project}},
    )
    calls = []

    async def run(argv, timeout):
        requested = json.loads(argv[5])["project_id"]
        calls.append((argv[3], argv[4], requested))
        if argv[3] == "voice-presets":
            cfg.accounts["one"]["project"] = changed_project
            rows = [{"voice": "Charon", "description": "Informative"}]
        else:
            rows = [
                {
                    "ref": "33333333-3333-4333-8333-333333333333",
                    "project_id": requested,
                    "workflow_id": "44444444-4444-4444-8444-444444444444",
                    "display_name": "Fixture",
                }
            ]
        return 0, json.dumps({"status": "ok", "voices": rows}).encode()

    monkeypatch.setattr("gflow_cli.selfhost.server.subprocess_run", run)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.get("/v1/google-flow/voices?email=account-one", headers=AUTH)
    assert response.status_code == 409
    assert calls == [("voice-presets", "one", project), ("voice-saved-list", "one", project)]
