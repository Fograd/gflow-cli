"""Explicit private REST catalog resume and persistent observation proof."""

import os
from urllib.parse import quote

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("../features/native_catalog_resume_rest.feature")


def require(ok, message):
    if not ok:
        pytest.fail(message, pytrace=False)


def read(case, params):
    try:
        response = case["client"].get(
            "/v1/google-flow/assets/projects/" + quote(case["account"], safe=""), params=params
        )
    except Exception:
        pytest.fail("Authenticated catalog read failed", pytrace=False)
    require(response.status_code == 200, "Fresh native catalog read was refused")
    try:
        result = response.json()
    except ValueError:
        pytest.fail("Native catalog reply is not JSON", pytrace=False)
    require(isinstance(result, dict), "Catalog response must be an object")
    return result


@given("a private REST account with an explicit existing owned character", target_fixture="case")
def configured():
    keys = ("URL", "TOKEN", "ACCOUNT", "PROJECT", "CHARACTER")
    values = {key: os.getenv("GFLOW_CLI_E2E_CATALOG_REST_" + key, "") for key in keys}
    if os.getenv("GFLOW_CLI_E2E_CATALOG_REST") != "1" or not all(values.values()):
        pytest.skip("Explicit private REST catalog and owned character fixture required")
    with httpx.Client(
        base_url=values["URL"],
        headers={"Authorization": "Bearer " + values["TOKEN"]},
        timeout=180,
        follow_redirects=False,
    ) as client:
        yield {
            "client": client,
            "account": values["ACCOUNT"],
            "project": values["PROJECT"],
            "character": values["CHARACTER"],
        }


@when("the selected project catalog is resumed twice and its observations are merged")
def perform(case):
    params = {
        "source": "google",
        "includeCatalogs": "true",
        "catalogProjectIds": case["project"],
        "maxProjects": "1",
    }
    first = read(case, params)
    second = read(case, params)
    for result in (first, second):
        require(
            result.get("catalogResume") is True and result.get("pagesRead") == 0,
            "Explicit catalog resume must not fabricate account pages",
        )
        require(
            result.get("paginationExhausted") is None and result.get("complete") is None,
            "Catalog resume must not claim account completeness",
        )
        catalogs = result.get("projectCatalogs")
        require(
            isinstance(catalogs, list) and len(catalogs) == 1,
            "Resume must return exactly one selected catalog",
        )
        catalog = catalogs[0]
        require(
            catalog.get("project_id") == case["project"],
            "Fresh resumed catalog must match selected project",
        )
        require(
            any(row.get("entity_id") == case["character"] for row in catalog.get("characters", [])),
            "Owned character must appear freshly",
        )
        observed = result.get("inventoryObservations", {})
        require(
            observed.get("projects", 0) >= 1 and observed.get("characters", 0) >= 1,
            "REST must persist project and character observations",
        )
        require(observed.get("complete") is None, "Observed counts cannot imply completeness")
    case["first"] = first["inventoryObservations"]
    case["second"] = second["inventoryObservations"]


@then("repeated fresh reads preserve observed counts without duplicate characters")
def checked(case):
    require(
        case["first"] == case["second"],
        "Repeated observed metadata must preserve idempotent counts",
    )
