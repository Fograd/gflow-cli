"""Opt-in free character lifecycle; mutates only a uniquely named test entity."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("../features/selfhost_native_character.feature")


@pytest.fixture
def character_case() -> Any:
    case: dict[str, Any] = {}
    yield case
    if case.get("ref"):
        with httpx.Client(timeout=240, trust_env=False, headers=case["headers"]) as client:
            response = client.delete(
                case["url"] + "/characters/" + case["ref"], params=case["controls"]
            )
            assert response.status_code == 200, "Owned test entity cleanup failed"


@given("an authenticated character endpoint and a registered native image")
def endpoint(character_case: dict[str, Any]) -> None:
    url = os.environ.get("GFLOW_SELFHOST_E2E_URL")
    token = os.environ.get("GFLOW_DAEMON_TOKEN")
    if not url or not token:
        pytest.skip("Authenticated deployed endpoint required")
    case = character_case
    case.update(url=url.rstrip("/"), headers={"Authorization": "Bearer " + token})
    with httpx.Client(timeout=240, trust_env=False, headers=case["headers"]) as client:
        response = client.get(case["url"] + "/accounts")
        response.raise_for_status()
        email, account = next(iter(response.json().items()))
        controls = {"email": email, "projectId": account["projectId"]}
        local = client.get(
            case["url"] + "/assets/media/" + email,
            params={"projectId": account["projectId"], "limit": 100},
        )
        native = client.get(
            case["url"] + "/assets/media/" + email,
            params={"projectId": account["projectId"], "source": "google", "limit": 100},
        )
        local.raise_for_status()
        native.raise_for_status()
        active = {row["mediaGenerationId"] for row in native.json()["media"] if not row["archived"]}
        images = [
            row["mediaGenerationId"]
            for row in local.json()["media"]
            if row.get("mediaGenerationId") in active
            and row["mimeType"] in ("image/png", "image/jpeg")
        ]
        if not images:
            pytest.skip("No registered native project image is available")
        case.update(
            controls=controls, image=images[0], name="API verification " + uuid.uuid4().hex[:12]
        )


@when("the API caller creates and edits a uniquely named character")
def lifecycle(character_case: dict[str, Any]) -> None:
    case = character_case
    with httpx.Client(timeout=240, trust_env=False, headers=case["headers"]) as client:
        response = client.post(
            case["url"] + "/characters",
            json={
                **case["controls"],
                "displayName": case["name"],
                "imageReference_1": case["image"],
                "personalityNotes": "Initial verification notes",
            },
        )
        if response.status_code == 502:
            partial = response.json().get("detail", {})
            if isinstance(partial, dict) and partial.get("createdCharacterRef"):
                case["ref"] = partial["createdCharacterRef"]
        response.raise_for_status()
        case["ref"] = response.json()["character"]["ref"]
        assert response.json()["character"]["personalityNotes"] == "Initial verification notes"
        response = client.patch(
            case["url"] + "/characters/" + case["ref"],
            json={**case["controls"], "personalityNotes": "Calm verification character"},
        )
        response.raise_for_status()


@then("the character retains its image and notes and can be removed while the source remains")
def verify(character_case: dict[str, Any]) -> None:
    case = character_case
    with httpx.Client(timeout=240, trust_env=False, headers=case["headers"]) as client:
        response = client.get(case["url"] + "/characters/" + case["ref"], params=case["controls"])
        response.raise_for_status()
        character = response.json()
        assert character["displayName"] == case["name"]
        assert character["personalityNotes"] == "Calm verification character"
        assert character["workflowIds"]
        response = client.delete(
            case["url"] + "/characters/" + case["ref"], params=case["controls"]
        )
        response.raise_for_status()
        assert response.json()["deleted"] == [case["ref"]]
        ref = case.pop("ref")
        assert (
            client.get(case["url"] + "/characters/" + ref, params=case["controls"]).status_code
            == 404
        )
        media = client.get(
            case["url"] + "/assets/media/" + case["controls"]["email"],
            params={"projectId": case["controls"]["projectId"], "source": "google", "limit": 100},
        )
        media.raise_for_status()
        assert any(
            row["mediaGenerationId"] == case["image"] and not row["archived"]
            for row in media.json()["media"]
        )
