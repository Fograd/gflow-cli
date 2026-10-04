"""Read-only deployed REST proof; never creates a Google resource."""

import io
import os

import httpx
import pytest
from PIL import Image
from pytest_bdd import given, scenarios, then, when

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]
scenarios("../features/native_image_raw.feature")


@given("an explicitly selected remote native image and account", target_fixture="case")
def configured():
    names = ("RAW_BASE", "RAW_ACCOUNT", "RESOURCES_PROJECT", "RAW_MEDIA", "RAW_WIDTH", "RAW_HEIGHT")
    values = {name: os.getenv("GFLOW_CLI_E2E_" + name) for name in names}
    token = os.getenv("GFLOW_DAEMON_TOKEN")
    if not all(values.values()) or not token or os.getenv("GFLOW_CLI_E2E_IMAGE_RAW") != "1":
        pytest.skip("Explicit remote image/account/project and bearer configuration required")
    return {**values, "token": token}


@when("its fresh URL and raw image bytes are requested")
def read(case):
    with httpx.Client(
        headers={"Authorization": "Bearer " + case["token"]}, timeout=210, trust_env=False
    ) as client:
        path = case["RAW_BASE"].rstrip("/") + "/v1/google-flow/assets/" + case["RAW_MEDIA"]
        params = {
            "source": "google",
            "email": case["RAW_ACCOUNT"],
            "projectId": case["RESOURCES_PROJECT"],
        }
        metadata = client.get(path, params=params)
        assert metadata.status_code == 200, "Fresh native metadata read failed"
        body = metadata.json()
        assert body["mediaGenerationId"] == case["RAW_MEDIA"] and body["url"].startswith(
            "https://flow-content.google/image/"
        )
        raw = client.get(path, params={**params, "raw": "true"})
        assert raw.status_code == 200, "Fresh native raw read failed"
        case["metadata_cache"] = metadata.headers.get("cache-control")
        case["raw_cache"] = raw.headers.get("cache-control")
        case["mime"] = raw.headers.get("content-type")
        case["bytes"] = raw.content


@then("the decoded bytes match fresh native dimensions and responses are not cached")
def verified(case):
    assert case["metadata_cache"] == case["raw_cache"] == "no-store"
    assert case["mime"] in ("image/png", "image/jpeg")
    with Image.open(io.BytesIO(case["bytes"])) as image:
        image.load()
        assert image.format in ("PNG", "JPEG")
        assert image.size == (int(case["RAW_WIDTH"]), int(case["RAW_HEIGHT"]))
