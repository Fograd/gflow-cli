"""Supplied generic video worker dispatch and masked checkpoints, no Google."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_server import settings

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
W = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ok", "unknown", "malformed"])
async def test_generic_private_worker_and_cleanup(tmp_path, monkeypatch, outcome):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    directory = tmp_path / "captcha-input"
    directory.mkdir()
    secret = directory / ("a" * 64 + ".token")
    secret.write_text("private-test-token-abcdefghijklmnopqrstuvwxyz")
    secret.chmod(0o600)
    store.submit(
        "videos",
        "pro1",
        {
            "project": P,
            "prompt": "simple test",
            "aspectRatio": "16:9",
            "count": 1,
            "model": "veo-3.1-lite",
            "captchaSecret": str(secret),
        },
        None,
    )
    job = store.claim("pro1")
    seen = []

    async def subprocess(args, timeout):
        assert args[2] == "gflow_cli.selfhost.general_video_worker"
        path = Path(args[-1])
        seen.append(path)
        assert path.stat().st_mode & 0o777 == 0o600
        payload = json.loads(path.read_text())
        assert payload["captchaSecret"] == str(secret)
        assert "private-test-token" not in " ".join(args)
        if outcome == "ok":
            video = path.parent / "video.mp4"
            video.write_bytes(b"test-output")
            return 0, json.dumps(
                {
                    "status": "ok",
                    "media_id": M,
                    "local_path": str(video),
                    "captchaProvider": "supplied",
                }
            ).encode()
        return 40, json.dumps(
            {
                "error": {
                    "class": "GeneralVideoOutcomeUnknown",
                    "outcome_unknown": True,
                    "project_id": P if outcome == "unknown" else W,
                    "media_ids": [M],
                    "workflow_ids": [W],
                    "phase": "video_poll",
                    "detail": "private-unsafe-value",
                }
            }
        ).encode()

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    result = await runtime.execute(cfg, store, job)
    assert all(not path.exists() for path in seen)
    assert not secret.exists()
    assert "private-unsafe-value" not in json.dumps(result)
    if outcome == "ok":
        assert result["captchaProvider"] == "supplied"
        assert result["media"][0]["mediaGenerationId"] == M
    elif outcome == "unknown":
        assert result["outcomeUnknown"] is True
        assert result["knownMediaGenerationIds"] == [M]
        assert store.get(job["id"])["knownMediaGenerationIds"] == [M]
    else:
        assert result["error"]["code"] == "gflow_command_failed"
        assert "knownMediaGenerationIds" not in result
