import json
import uuid

import pytest

from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.runtime import execute
from gflow_cli.selfhost.store import Store


@pytest.mark.parametrize("received", [3, 4, 5])
async def test_image_result_count_matches_request_and_preserves_outputs(
    tmp_path, monkeypatch, received
):
    project = "11111111-1111-4111-8111-111111111111"
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
            "count": 4,
            "model": "nano-banana-2",
            "aspectRatio": "1:1",
        },
        None,
    )
    calls = []
    ids = []

    async def run(args, timeout):
        calls.append(args)
        assert args[args.index("--count") + 1] == "4"
        out = tmp_path / "output" / job["jobId"]
        images = []
        for _ in range(received):
            media = str(uuid.uuid4())
            ids.append(media)
            path = out / (media + ".jpg")
            path.write_bytes(b"\xff\xd8\xfffixture")
            images.append({"media_name": media, "local_path": str(path)})
        return 0, json.dumps({"status": "ok", "images": images}).encode()

    monkeypatch.setattr("gflow_cli.selfhost.runtime.subprocess_run", run)
    result = await execute(cfg, store, store.claim("pro1"))
    assert len(calls) == 1
    assert len(result["media"]) == received
    assert all(store.asset_get(media)["profile"] == "pro1" for media in ids)
    if received == 4:
        assert "error" not in result
    else:
        assert result["error"] == {
            "code": "image_output_count_mismatch",
            "expectedCount": 4,
            "receivedCount": received,
            "retryable": False,
            "detail": (
                "Preserved returned images; inspect the job before submitting another generation."
            ),
        }
