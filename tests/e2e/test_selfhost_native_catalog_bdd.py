"""Read-only live HTTP catalog regression; no generation or provider tasks."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("../features/selfhost_native_catalog.feature")


@given("an authenticated native catalog endpoint", target_fixture="catalog")
def endpoint() -> dict[str, Any]:
    url = os.environ.get("GFLOW_SELFHOST_E2E_URL")
    token = os.environ.get("GFLOW_DAEMON_TOKEN")
    if not url or not token:
        pytest.skip("Authenticated deployed endpoint required")
    return {"url": url.rstrip("/"), "headers": {"Authorization": "Bearer " + token}}


@when("the tool reads native projects, characters and system voices")
def read_catalogs(catalog: dict[str, Any]) -> None:
    with httpx.Client(timeout=90, trust_env=False, headers=catalog["headers"]) as client:
        base = catalog["url"]
        accounts = client.get(base + "/accounts")
        accounts.raise_for_status()
        email, account = next(iter(accounts.json().items()))
        projects = client.get(base + "/assets/projects/" + email, params={"source": "google"})
        projects.raise_for_status()
        catalog["projects"] = projects.json()
        cursor = catalog["projects"]["cursor"]
        if cursor:
            page = client.get(
                base + "/assets/projects/" + email, params={"source": "google", "cursor": cursor}
            )
            page.raise_for_status()
            catalog["next"] = page.json()
        params = {"email": email, "projectId": account["projectId"]}
        characters = client.get(base + "/characters", params=params)
        characters.raise_for_status()
        voices = client.get(
            base + "/voices", params={**params, "catalog": "google", "source": "system"}
        )
        voices.raise_for_status()
        catalog.update(
            characters=characters.json(), voices=voices.json(), project=account["projectId"]
        )


@then("native identities, pagination and voice sources are preserved")
def verify(catalog: dict[str, Any]) -> None:
    projects = catalog["projects"]["projects"]
    assert projects and all(row["projectId"] for row in projects)
    if "next" in catalog:
        assert {row["projectId"] for row in projects}.isdisjoint(
            {row["projectId"] for row in catalog["next"]["projects"]}
        )
    assert catalog["voices"]["voices"]
    assert all(row["source"] == "system" for row in catalog["voices"]["voices"])
    assert all(
        row["projectId"] == catalog["project"] for row in catalog["characters"]["characters"]
    )
    assert "signed" not in str(catalog["projects"])
