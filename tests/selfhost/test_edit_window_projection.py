import pytest

from gflow_cli.selfhost.http_jobs import result_record


@pytest.mark.parametrize("duration", [8, 8.125, None])
def test_edit_window_survives_public_result(duration):
    result = dict(startFrameIndex=12, endFrameIndex=192, sourceDurationSeconds=duration)
    safe = result_record(result, kind="videos/edit")
    assert safe["startFrameIndex"] == 12
    assert safe["endFrameIndex"] == 192
    if duration is None:
        assert "sourceDurationSeconds" not in safe
    else:
        assert safe["sourceDurationSeconds"] == duration


@pytest.mark.parametrize("kind", [None, "videos/reference", "images"])
def test_edit_window_does_not_expand_other_routes(kind):
    assert (
        result_record(
            dict(startFrameIndex=0, endFrameIndex=192, sourceDurationSeconds=8), kind=kind
        )
        == {}
    )


@pytest.mark.parametrize(
    "start,end", [(True, 192), (0, False), (-1, 12), (20, 10), (0, 241), (0, "192")]
)
def test_invalid_edit_window_not_exposed(start, end):
    assert (
        result_record(
            dict(startFrameIndex=start, endFrameIndex=end, sourceDurationSeconds=8),
            kind="videos/edit",
        )
        == {}
    )


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), True, -1, "8", 10**500])
def test_invalid_source_duration_dropped(duration):
    safe = result_record(
        dict(startFrameIndex=0, endFrameIndex=192, sourceDurationSeconds=duration),
        kind="videos/edit",
    )
    assert safe == dict(startFrameIndex=0, endFrameIndex=192)


@pytest.mark.asyncio
async def test_edit_worker_window_survives_runtime_and_job(tmp_path, monkeypatch):
    import json

    from gflow_cli.selfhost import runtime
    from gflow_cli.selfhost.http_jobs import job_record
    from gflow_cli.selfhost.store import Store
    from tests.selfhost.test_server import settings

    project = "11111111-1111-4111-8111-111111111111"
    media = "22222222-2222-4222-8222-222222222222"
    workflow = "33333333-3333-4333-8333-333333333333"
    source = "44444444-4444-4444-8444-444444444444"
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    payload = dict(project=project, referenceVideo_1=source, prompt="test")
    store.submit("videos/edit", "pro1", payload, None)
    job = store.claim("pro1")

    async def run(*args):
        path = cfg.root / "output" / job["id"] / "video.mp4"
        path.write_bytes(b"fixture")
        return 0, json.dumps(
            dict(
                type="video_edit_result",
                project_id=project,
                startFrameIndex=12,
                endFrameIndex=192,
                sourceDurationSeconds=8,
                privateUrl="signed-secret-url",
                results=[dict(media_id=media, workflow_id=workflow, local_path=str(path))],
            )
        ).encode()

    monkeypatch.setattr(runtime, "subprocess_run", run)
    result = await runtime.execute(cfg, store, job)
    public = job_record(dict(job, state="completed"), payload, result)
    assert public["response"]["startFrameIndex"] == 12
    assert public["response"]["endFrameIndex"] == 192
    assert public["response"]["sourceDurationSeconds"] == 8
    assert "signed-secret" not in json.dumps(public)
