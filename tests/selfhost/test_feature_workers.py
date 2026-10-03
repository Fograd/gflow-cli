import json
from pathlib import Path

import pytest

from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.store import Store
from tests.selfhost.test_server import settings

P = "11111111-1111-4111-8111-111111111111"
M = "22222222-2222-4222-8222-222222222222"
OUTPUT_ID = "44444444-4444-4444-8444-444444444444"
W = "55555555-5555-4555-8555-555555555555"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,module",
    [
        ("videos/extend", "gflow_cli.selfhost.extension_worker"),
        ("videos/edit", "gflow_cli.selfhost.native_video_edit_worker"),
        ("videos/reference", "gflow_cli.selfhost.reference_video_worker"),
    ],
)
async def test_video_worker_outputs_become_downloadable_assets(tmp_path, monkeypatch, kind, module):
    cfg = settings(tmp_path)
    store = Store(tmp_path)
    job = store.submit(
        kind, "pro1", {"project": P, "mediaGenerationId": M, "referenceVideo_1": M}, None
    )
    claimed = store.claim("pro1")

    async def run(args, timeout):
        assert args[2] == module
        request = Path(args[-1])
        assert request.is_file()
        path = request.parent / "edited.mp4"
        path.write_bytes(b"MP4 test bytes")
        return 0, json.dumps(
            {
                "type": "video_reference_result"
                if kind == "videos/reference"
                else "video_edit_result"
                if kind == "videos/edit"
                else "video_extension_result",
                "project_id": P,
                "results": [{"media_id": OUTPUT_ID, "workflow_id": W, "local_path": str(path)}],
            }
        ).encode()

    monkeypatch.setattr(runtime, "subprocess_run", run)
    result = await runtime.execute(cfg, store, claimed)
    assert result["media"][0]["mediaGenerationId"] == OUTPUT_ID
    assert result["media"][0]["downloadPath"].endswith(OUTPUT_ID + "/download")
    assert store.asset_get(OUTPUT_ID)["profile"] == "pro1"
    assert store.asset_get(OUTPUT_ID)["mime"] == "video/mp4"
    assert not (tmp_path / "output" / job["jobId"] / "request.json").exists()
