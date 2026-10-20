"""Opt-in real REST reference acceptance; each allowance is consumed once."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

scenarios("../features/rest_uploaded_references.feature")


def _save(path: Path, data: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(data, stream)


@given("a private authorized REST reference case with an unused allowance", target_fixture="case")
def authorized_case() -> dict[str, Any]:
    name = os.environ.get("GFLOW_CLI_E2E_REST_REFERENCE_CASE")
    if not name:
        pytest.skip("Explicit private REST reference acceptance case required")
    path = Path(name)
    assert path.stat().st_mode & 0o077 == 0, "Case contains protected endpoint credentials"
    case = json.loads(path.read_text())
    assert case["url"].startswith("http://127.0.0.1:"), "Acceptance endpoint must be loopback"
    for queue in (case["queue_db"], str(Path(case["root"]) / "jobs.sqlite3")):
        with sqlite3.connect(Path(queue).as_uri() + "?mode=ro", uri=True) as db:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE state IN ('created','running')"
                ).fetchone()[0]
                == 0
            ), "Both queues must be idle"
    output = Path(case["output"])
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output / "allowance.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump({"case": case["case_id"], "reservedAt": time.time()}, stream)
    return case


@when("two reference assets and one image request use the selected account")
def execute_case(case: dict[str, Any]) -> None:
    output = Path(case["output"])
    headers = {"Authorization": "Bearer " + case["token"]}
    identifiers = []
    with httpx.Client(timeout=660, headers=headers) as client:
        for index, source in enumerate(case["refs"], 1):
            path = Path(source)
            assert path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png")
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            response = client.post(
                case["url"] + "/assets/" + quote(case["email"], safe=""),
                content=path.read_bytes(),
                headers={"Content-Type": mime},
            )
            receipt = response.json()
            _save(output / f"upload-{index}.json", receipt)
            assert response.status_code == 200, "Inspect protected upload receipt; do not replay"
            assert receipt["email"].casefold() == case["email"].casefold()
            assert receipt["projectId"] == case["project"]
            identifier = str(UUID(receipt["mediaGenerationId"]["mediaGenerationId"]))
            identifiers.append(identifier)
        assert len(identifiers) == 2
        payload = {
            "prompt": case["prompt"],
            "model": "nano-banana-2.1",
            "aspectRatio": "3:4",
            "count": 1,
            "async": True,
            "email": case["email"],
            "reference_1": identifiers[0],
            "reference_2": identifiers[1],
        }
        response = client.post(
            case["url"] + "/images",
            json=payload,
            headers={"Idempotency-Key": case["case_id"]},
        )
        receipt = response.json()
        _save(output / "submission.json", receipt)
        assert response.status_code in (200, 201, 202), "Inspect receipt; do not replay"
        case["job"] = receipt["jobId"]
        case["references"] = identifiers
        deadline = time.monotonic() + 660
        while receipt.get("status") not in ("completed", "failed", "interrupted"):
            assert time.monotonic() < deadline, "Existing job remains authoritative; do not replay"
            time.sleep(2)
            response = client.get(case["url"] + "/jobs/" + case["job"])
            assert response.status_code == 200
            receipt = response.json()
            _save(output / "job.json", receipt)
        case["receipt"] = receipt


@then("the queued references stay native and one image decodes")
def verify_case(case: dict[str, Any]) -> None:
    output = Path(case["output"])
    receipt = case["receipt"]
    assert receipt["status"] == "completed", "Inspect existing job receipt; do not replay"
    with sqlite3.connect(
        (Path(case["root"]) / "jobs.sqlite3").as_uri() + "?mode=ro", uri=True
    ) as db:
        row = db.execute("SELECT profile,payload FROM jobs WHERE id=?", (case["job"],)).fetchone()
    assert row[0] == case["profile"]
    payload = json.loads(row[1])
    assert payload["email"].casefold() == case["email"].casefold()
    assert payload["project"] == case["project"]
    assert payload["_image_reference_sources"] == [
        {"id": identifier, "kind": "native"} for identifier in case["references"]
    ]
    media = receipt.get("response", receipt)["media"]
    assert len(media) == 1
    raw = base64.b64decode(media[0]["image"]["generatedImage"]["encodedImage"], validate=True)
    assert len(raw) > 10_000
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        assert image.format in ("PNG", "JPEG")
        width, height = image.size
    assert abs(width / height - 3 / 4) < 0.01
    (output / "output.jpg").write_bytes(raw)
    _save(
        output / "proof.json",
        {
            "case": case["case_id"],
            "jobId": case["job"],
            "status": receipt["status"],
            "references": case["references"],
            "nativeSources": True,
            "publicGenerationRequests": 1,
            "width": width,
            "height": height,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    )
