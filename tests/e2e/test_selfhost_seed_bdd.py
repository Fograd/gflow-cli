"""Live image-only regression: verify native returned seeds, not request echoes."""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

import httpx
import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

scenarios("../features/selfhost_seed.feature")


@pytest.fixture
def state() -> dict[str, Any]:
    return {}


@given("an authenticated seeded-image REST endpoint")
def endpoint(state: dict[str, Any]) -> None:
    url = os.environ.get("GFLOW_SELFHOST_E2E_URL")
    token = os.environ.get("GFLOW_DAEMON_TOKEN")
    if not url or not token:
        pytest.skip("Authenticated deployed endpoint required")
    state.update(url=url.rstrip("/"), headers={"Authorization": "Bearer " + token})


@when("a caller requests two images with seed 12042")
def generate(state: dict[str, Any]) -> None:
    with httpx.Client(headers=state["headers"], timeout=120, trust_env=False) as client:
        response = client.post(
            state["url"] + "/images",
            json={
                "prompt": "A small wooden sailboat on calm blue water, simple studio illustration",
                "model": "nano-banana-2",
                "count": 2,
                "seed": 12042,
                "aspectRatio": "1:1",
                "async": True,
            },
        )
        assert response.status_code == 201
        job = response.json()
        deadline = time.monotonic() + 240
        while job["status"] in ("created", "started") and time.monotonic() < deadline:
            time.sleep(1)
            response = client.get(state["url"] + "/jobs/" + job["jobId"])
            response.raise_for_status()
            job = response.json()
        assert job["status"] == "completed", job.get("error")
        state["job"] = job


@then("both Google image results report the requested seed sequence")
def verify(state: dict[str, Any]) -> None:
    media = state["job"]["response"]["media"]
    assert len(media) == 2
    assert sorted(item["image"]["generatedImage"]["seed"] for item in media) == [12042, 12043]
    for item in media:
        data = base64.b64decode(item["image"]["generatedImage"]["encodedImage"], validate=True)
        with Image.open(io.BytesIO(data)) as image:
            assert image.width >= 1024 and image.height >= 1024
