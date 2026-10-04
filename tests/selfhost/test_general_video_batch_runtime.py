import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_generic_video_batch_output import M, P, W, output
from tests.selfhost.test_server import settings


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ok", "partial", "killed"])
async def test_count_two_dispatches_once_and_projects_all_handles(tmp_path, monkeypatch, outcome):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    store.submit(
        "videos",
        "pro1",
        {
            "project": P,
            "prompt": "test",
            "aspectRatio": "16:9",
            "count": 2,
            "model": "veo-3.1-lite",
        },
        None,
    )
    job = store.claim("pro1")
    seen = []

    async def run(args, timeout):
        assert args[2] == "gflow_cli.selfhost.general_video_worker"
        request = Path(args[-1])
        seen.append(request)
        data = json.loads(request.read_text())
        assert data["count"] == 2
        if outcome == "ok":
            return 0, json.dumps(output(request.parent)).encode()
        if outcome == "killed":
            (request.parent / "video-checkpoint.json").write_text(
                json.dumps(
                    {"project_id": P, "media_ids": M, "workflow_ids": W, "phase": "video_poll"}
                )
            )
            return 137, b""
        return 40, json.dumps(
            {
                "error": {
                    "class": "GeneralVideoOutcomeUnknown",
                    "project_id": P,
                    "media_ids": M[:1],
                    "workflow_ids": W[:1],
                    "phase": "video_submit",
                    "outcome_unknown": True,
                }
            }
        ).encode()

    monkeypatch.setattr(runtime, "subprocess_run", run)
    monkeypatch.setattr(
        "gflow_cli.selfhost.video_batch_output.probe",
        AsyncMock(return_value=SimpleNamespace(width=1280, height=720, duration=8)),
    )
    result = await runtime.execute(cfg, store, job)
    assert len(seen) == 1 and not seen[0].exists()
    if outcome == "ok":
        assert [item["mediaGenerationId"] for item in result["media"]] == M
        assert result["requestedCount"] == 2 and result["completedCount"] == 2
    else:
        assert result["outcomeUnknown"] is True
        assert result["knownMediaGenerationIds"] == (M if outcome == "killed" else M[:1])
        assert result["error"]["retryable"] is False
