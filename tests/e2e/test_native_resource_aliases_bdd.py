"""Opt-in real REST resource alias proof; no TTS, generation or Google mutation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("../features/native_resource_aliases.feature")


@dataclass(repr=False)
class ResourceCase:
    client: httpx.Client
    account: str = field(repr=False)
    project: str = field(repr=False)
    native_id: str = field(repr=False)
    kind: str
    alias: str = field(repr=False)
    workflow_id: str | None = field(default=None, repr=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


def request(case: ResourceCase, method: str, path: str, **kwargs) -> httpx.Response:
    try:
        return case.client.request(method, path, **kwargs)
    except Exception:
        pytest.fail("Authenticated resource alias request failed", pytrace=False)


def resource_path(case: ResourceCase, identifier: str) -> str:
    collection = "characters" if case.kind == "character" else "voices"
    return "/v1/google-flow/" + collection + "/" + quote(identifier, safe="")


def mapping_path(case: ResourceCase) -> str:
    return resource_path(case, case.account) + "/aliases/" + quote(case.alias, safe="")


def body(response: httpx.Response) -> dict:
    try:
        value = response.json()
    except ValueError:
        pytest.fail("Resource alias response is not JSON", pytrace=False)
    require(isinstance(value, dict), "Resource alias response must be an object")
    return value


@pytest.fixture
def rest_resource_case():
    keys = (
        "API_URL",
        "TOKEN",
        "ACCOUNT",
        "PROJECT",
        "CHARACTER_ID",
        "CHARACTER_IMAGE_COUNT",
        "VOICE_AUDIO_ID",
        "VOICE_WORKFLOW_ID",
    )
    values = {key: os.getenv("GFLOW_CLI_E2E_RESOURCE_ALIAS_" + key, "") for key in keys}
    if os.getenv("GFLOW_CLI_E2E_RESOURCE_ALIAS_REST") != "1" or not all(
        values[key] for key in keys[:4]
    ):
        pytest.skip("Explicit authenticated REST resource alias opt-in required")
    parsed = urlsplit(values["API_URL"])
    require(parsed.scheme in {"http", "https"} and bool(parsed.hostname), "Invalid private API URL")
    require(
        not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
        "API URL must not contain credentials or query data",
    )
    with httpx.Client(
        base_url=values["API_URL"].rstrip("/"),
        headers={"Authorization": "Bearer " + values["TOKEN"]},
        timeout=150,
        follow_redirects=False,
    ) as client:
        cases = []
        yield values, client, cases
        for case in cases:
            removed = request(case, "DELETE", mapping_path(case))
            require(removed.status_code in {200, 404}, "Local resource alias cleanup failed")


@given(
    parsers.parse("an explicit authenticated REST account with an existing owned {kind} resource"),
    target_fixture="case",
)
def configured(rest_resource_case, kind):
    values, client, cases = rest_resource_case
    prefix = "user:bdd_" + uuid4().hex + "-email:opaque-"
    if kind == "character":
        native_id = values["CHARACTER_ID"]
        if not native_id:
            pytest.skip("Explicit existing owned character fixture required")
        count = values["CHARACTER_IMAGE_COUNT"]
        require(count in {"1", "2"}, "Explicit character image count must be one or two")
        alias = prefix + "character:" + native_id + "-imgs:" + count
        workflow = None
    else:
        native_id, workflow = values["VOICE_AUDIO_ID"], values["VOICE_WORKFLOW_ID"]
        if not native_id or not workflow:
            pytest.skip("Explicit existing owned saved voice fixture required; no TTS is attempted")
        alias = prefix + "voice:" + workflow + "-mid:" + native_id
    case = ResourceCase(
        client, values["ACCOUNT"], values["PROJECT"], native_id, kind, alias, workflow
    )
    cases.append(case)
    return case


@when("an unknown resource alias is refused and the owned alias is registered and read")
def register_and_read(case):
    require(
        request(case, "GET", resource_path(case, case.alias)).status_code == 404,
        "Unknown resource alias must be refused",
    )
    payload = {"alias": case.alias, "projectId": case.project}
    if case.kind == "character":
        payload["entityId"] = case.native_id
    else:
        payload.update(mediaId=case.native_id, workflowId=case.workflow_id)
    registered = request(case, "POST", resource_path(case, case.account) + "/aliases", json=payload)
    require(registered.status_code == 201, "Fresh owned resource alias registration failed")
    item = body(registered)
    require(
        item.get("ref") == case.alias
        and item.get("nativeRef") == case.native_id
        and item.get("kind") == case.kind
        and item.get("projectId") == case.project
        and item.get("verified") is True,
        "Registration must preserve exact native resource binding",
    )
    response = request(case, "GET", resource_path(case, case.alias))
    require(response.status_code == 200, "Fresh resource alias GET failed")
    require(response.headers.get("cache-control") == "no-store", "Resource detail must be no-store")
    item = body(response)
    require(
        item.get("ref") == case.alias and item.get("nativeRef") == case.native_id,
        "Fresh GET must preserve alias and native identity",
    )


@then("local resource alias removal preserves the original native resource")
def remove_and_read_original(case):
    removed = request(case, "DELETE", mapping_path(case))
    require(removed.status_code == 200, "Local resource alias deletion failed")
    item = body(removed)
    require(
        item.get("removed") is True
        and item.get("googleResourceDeleted") is False
        and item.get("scope") == "local-alias",
        "Deletion must remove only the resource mapping",
    )
    require(
        request(case, "GET", resource_path(case, case.alias)).status_code == 404,
        "Removed resource alias must be unavailable",
    )
    response = request(
        case,
        "GET",
        resource_path(case, case.native_id),
        params={
            "email": case.account,
            "projectId": case.project,
            "source": "google" if case.kind == "character" else "user",
        },
    )
    require(response.status_code == 200, "Original owned native resource must remain readable")
    require(
        response.headers.get("cache-control") == "no-store",
        "Original resource detail must be no-store",
    )
    require(
        body(response).get("ref") == case.native_id,
        "Original resource identity must remain unchanged",
    )
