"""Opt-in HTTP proof. Generates two images; no video credits are spent."""

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

scenarios("../features/selfhost_rest.feature")


@pytest.fixture
def workflow() -> dict[str, Any]:
    return {}


@given("an authenticated self-hosted Flow REST endpoint")
def endpoint(workflow: dict[str, Any]) -> None:
    url = os.environ.get("GFLOW_SELFHOST_E2E_URL", "")
    token = os.environ.get("GFLOW_DAEMON_TOKEN", "")
    if not url or not token:
        pytest.skip("GFLOW_SELFHOST_E2E_URL and GFLOW_DAEMON_TOKEN are required")
    workflow["url"] = url.rstrip("/")
    workflow["headers"] = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=10, trust_env=False) as client:
        assert client.get(url + "/accounts").status_code == 401
        response = client.get(url + "/accounts", headers=workflow["headers"])
        response.raise_for_status()
        assert response.json()


def completed(workflow: dict[str, Any], path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=120, trust_env=False, headers=workflow["headers"]) as client:
        accepted = client.post(workflow["url"] + path, json=payload)
        assert accepted.status_code == 200
        job = accepted.json()["jobId"]
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            response = client.get(workflow["url"] + "/jobs/" + job)
            response.raise_for_status()
            result = response.json()
            assert result["status"] not in ("failed", "interrupted")
            if result["status"] == "completed":
                return result
            time.sleep(1)
    pytest.fail("REST job did not complete within 240 seconds")


def pixels(result: dict[str, Any]) -> bytes:
    return base64.b64decode(
        result["media"][0]["image"]["generatedImage"]["encodedImage"], validate=True
    )


@when("a tool generates an image through HTTP")
def generate(workflow: dict[str, Any]) -> None:
    result = completed(
        workflow,
        "/images",
        {
            "prompt": "A single red ceramic mug on a plain white table, studio photo, no text.",
            "model": "nano-banana-2",
            "aspectRatio": "1:1",
            "count": 1,
        },
    )
    workflow["initial"] = pixels(result)
    workflow["email"] = result["email"]


@when("uploads the image and generates a referenced variation")
def reference(workflow: dict[str, Any]) -> None:
    with httpx.Client(timeout=120, trust_env=False, headers=workflow["headers"]) as client:
        uploaded = client.post(
            workflow["url"] + "/assets/" + workflow["email"],
            content=workflow["initial"],
            headers={"Content-Type": "image/jpeg"},
        )
        assert uploaded.status_code == 200
        media = uploaded.json()["mediaGenerationId"]["mediaGenerationId"]
    result = completed(
        workflow,
        "/images",
        {
            "prompt": "Keep the same scene and mug shape. Change the mug to cobalt blue.",
            "reference_1": media,
            "email": workflow["email"],
            "model": "nano-banana-2",
            "aspectRatio": "1:1",
            "count": 1,
        },
    )
    workflow["variation"] = result
    with Image.open(io.BytesIO(pixels(result))) as image:
        workflow["source_dimensions"] = image.size


@when("requests native 2K upscaling through HTTP")
def upscale(workflow: dict[str, Any]) -> None:
    result = completed(
        workflow,
        "/images/upscale",
        {
            "mediaGenerationId": workflow["variation"]["media"][0]["mediaGenerationId"],
            "resolution": "2k",
            "email": workflow["email"],
        },
    )
    with Image.open(io.BytesIO(pixels(result))) as image:
        workflow["upscaled_dimensions"] = image.size


@then("the upscale has twice the source width and height")
def dimensions(workflow: dict[str, Any]) -> None:
    assert workflow["upscaled_dimensions"] == tuple(
        dimension * 2 for dimension in workflow["source_dimensions"]
    )
