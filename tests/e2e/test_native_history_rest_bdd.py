"""Free real REST history proof; only account-owned reads and local metadata upserts."""

import os
from urllib.parse import quote

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("../features/native_history_rest.feature")


def require(condition, message):
    if not condition:
        pytest.fail(message, pytrace=False)


@given("an explicitly authenticated REST account history configuration", target_fixture="case")
def configured():
    values = {
        key: os.getenv("GFLOW_CLI_E2E_HISTORY_" + key, "")
        for key in ("API_URL", "TOKEN", "ACCOUNT")
    }
    if os.getenv("GFLOW_CLI_E2E_HISTORY_REST") != "1" or not all(values.values()):
        pytest.skip("Explicit private authenticated history REST configuration required")
    return values


@when("two native account history pages are requested through REST")
def read(case):
    try:
        response = httpx.get(
            case["API_URL"].rstrip("/")
            + "/v1/google-flow/assets/projects/"
            + quote(case["ACCOUNT"], safe=""),
            headers={"Authorization": "Bearer " + case["TOKEN"]},
            params={
                "source": "google",
                "includeHistory": "true",
                "historyMaxPages": "2",
                "historyMaxMedia": "40",
            },
            timeout=150,
            follow_redirects=False,
        )
    except Exception:
        pytest.fail("Private REST history request failed", pytrace=False)
    require(response.status_code == 200, "Fresh REST history read failed")
    try:
        case["result"] = response.json()
    except ValueError:
        pytest.fail("REST history response is not JSON", pytrace=False)


@then("history joins and persistent observation counts are returned without claiming completeness")
def verify(case):
    result = case["result"]
    history = result.get("accountHistory", {})
    require(history.get("pages_read") == 2, "Two account history pages were not read")
    media, workflows = history.get("media", []), history.get("workflows", [])
    require(len(media) == len(workflows) == 40, "Expected bounded history fixture is unavailable")
    owners = {row["workflow_id"]: row["project_id"] for row in workflows}
    require(
        all(owners.get(row["workflow_id"]) == row["project_id"] for row in media),
        "Fresh media/workflow project joins are inconsistent",
    )
    require(
        history.get("complete") is None and result.get("complete") is None,
        "History completeness must remain unknown",
    )
    observations = result.get("inventoryObservations", {})
    require(
        observations.get("media", 0) >= 40 and observations.get("workflows", 0) >= 40,
        "Durable observed metadata was not reconciled",
    )
    require(
        observations.get("complete") is None, "Observed synchronization must not claim completeness"
    )
    require(
        all(
            "url" not in row and "prompt" not in row and "caption" not in row
            for row in media + workflows
        ),
        "Private content fields must not enter history observations",
    )
