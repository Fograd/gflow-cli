import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gflow_cli.selfhost import runtime
from gflow_cli.selfhost.config import Settings
from gflow_cli.selfhost.server import create_app
from gflow_cli.selfhost.store import Store

PROJECT = "11111111-1111-4111-8111-111111111111"
IMAGE = "22222222-2222-4222-8222-222222222222"
ENTITY = "33333333-3333-4333-8333-333333333333"
AUTH = {"Authorization": "Bearer test-token"}


def setup(tmp_path):
    cfg = Settings(
        token="test-token",
        root=tmp_path,
        accounts={"one": {"email": "test@example.org", "project": PROJECT}},
        callbacks=(),
        sync_wait=0,
    )
    path = tmp_path / "managed.png"
    Image.new("RGB", (8, 8)).save(path)
    store = Store(tmp_path)
    store.asset(IMAGE, "one", PROJECT, str(path), "image/png")
    return cfg, store


def test_http_canonical_markers_preserve_repeated_positions_and_body_slots(tmp_path):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={
                "prompt": "@REFERENCE_3 then @character_1 then @reference_3",
                "reference_3": IMAGE,
                "character_1": ENTITY,
                "model": "nano-banana-2",
                "count": 1,
                "aspectRatio": "1:1",
                "async": True,
            },
        )
        assert response.status_code == 201, response.text
        payload = json.loads(store.claim("one")["payload"])
        plan = payload["reference_prompt_plan"]
        assert plan["image_ids"] == [IMAGE]
        assert plan["character_ids"] == [ENTITY]
        assert [span["slot"] for span in plan["spans"] if "slot" in span] == [
            "reference_3",
            "character_1",
            "reference_3",
        ]


def test_missing_marker_slot_http_refuses_before_queue(tmp_path):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": "@reference_2", "reference_1": IMAGE, "async": True},
        )
        assert response.status_code == 400
        assert not store.job_page(limit=10)["jobs"]


def test_unknown_marker_family_and_email_remain_literal(tmp_path):
    cfg, store = setup(tmp_path)
    prompt = "café@example.test @something_1 @referenceVideo_1"
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={"prompt": prompt, "async": True, "count": 1},
        )
        assert response.status_code == 201, response.text
        payload = json.loads(store.claim("one")["payload"])
        assert payload["prompt"] == prompt
        assert payload["reference_syntax"] == "slots"


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_marked_http_job_uses_private_worker_plan_not_plain_cli(
    tmp_path, monkeypatch, duplicate
):
    cfg, store = setup(tmp_path)
    with TestClient(create_app(cfg, start_workers=False)) as client:
        response = client.post(
            "/v1/google-flow/images",
            headers=AUTH,
            json={
                "prompt": "@reference_1 then @reference_1",
                **({"reference_2": IMAGE.upper()} if duplicate else {}),
                "reference_1": IMAGE,
                "count": 1,
                "model": "nano-banana-2",
                "async": True,
            },
        )
        assert response.status_code == 201
        job = store.claim("one")
    observed = {}

    async def subprocess(args, *a, **kw):
        assert "gflow_cli.selfhost.image_worker" in args
        path = Path(args[-1])
        assert path.stat().st_mode & 0o777 == 0o600
        observed.update(json.loads(path.read_text()))
        return 1, b""

    monkeypatch.setattr(runtime, "subprocess_run", subprocess)
    await runtime.execute(cfg, store, dict(job))
    assert observed["reference_prompt_plan"]["image_ids"] == [IMAGE]
    assert observed["refPaths"] == [str(tmp_path / "managed.png")]

    from gflow_cli.worker.codec import build_image_request

    typed = build_image_request(
        {
            **observed,
            "aspect": observed["aspectRatio"],
            "ref_paths": observed["refPaths"],
            "reference_entities": observed["reference_prompt_plan"]["character_ids"],
        }
    )
    assert typed.reference_prompt_plan.image_ids == (IMAGE,)
    assert len(typed.ref_paths) == 1
    assert typed.aspect == type(typed.aspect).from_cli(observed["aspectRatio"])
