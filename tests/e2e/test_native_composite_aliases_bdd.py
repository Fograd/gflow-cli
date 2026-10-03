"""Opt-in real REST alias lifecycle; local mapping writes and Google reads only."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("../features/native_composite_aliases.feature")


@dataclass(repr=False)
class AliasCase:
    client: httpx.Client
    account: str = field(repr=False)
    project: str = field(repr=False)
    media: str = field(repr=False)
    kind: str
    alias: str = field(repr=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


def request(case: AliasCase, method: str, path: str, **kwargs):
    try:
        return case.client.request(method, path, **kwargs)
    except Exception:
        pytest.fail("Authenticated REST alias request failed", pytrace=False)


def asset_path(identifier: str) -> str:
    return "/v1/google-flow/assets/" + quote(identifier, safe="")


def mapping_path(case: AliasCase) -> str:
    return asset_path(case.account) + "/aliases/" + quote(case.alias, safe="")


def metadata(response: httpx.Response) -> dict:
    require(response.status_code == 200, "Fresh native alias read did not succeed")
    require(response.headers.get("cache-control") == "no-store", "Native detail must be no-store")
    try:
        value = response.json()
    except ValueError:
        pytest.fail("Native metadata is not JSON", pytrace=False)
    require(isinstance(value, dict), "Native metadata must be an object")
    return value


@pytest.fixture
def rest_alias_case():
    values = {
        key: os.getenv("GFLOW_CLI_E2E_ALIAS_" + key, "")
        for key in ("API_URL", "TOKEN", "ACCOUNT", "PROJECT", "IMAGE_ID", "VIDEO_ID")
    }
    if os.getenv("GFLOW_CLI_E2E_ALIAS_REST") != "1" or not all(
        values[key] for key in ("API_URL", "TOKEN", "ACCOUNT", "PROJECT")
    ):
        pytest.skip("Explicit authenticated REST alias opt-in and private configuration required")
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
            response = request(case, "DELETE", mapping_path(case))
            require(response.status_code in {200, 404}, "Local alias cleanup failed")


@given(
    parsers.parse("an explicit authenticated REST account with an existing owned {kind} fixture"),
    target_fixture="case",
)
def configured(rest_alias_case, kind):
    values, client, cases = rest_alias_case
    media = values[kind.upper() + "_ID"]
    if not media:
        pytest.skip("Explicit existing owned fixture required for selected native media kind")
    alias = "user:bdd_" + uuid4().hex + "-email:opaque-" + kind + ":" + media
    case = AliasCase(client, values["ACCOUNT"], values["PROJECT"], media, kind, alias)
    cases.append(case)
    return case


@when("an unknown alias is checked and the fixture alias is registered and read")
def register_and_read(case):
    unknown = request(case, "GET", asset_path(case.alias), params={"source": "google"})
    require(unknown.status_code == 404, "Unknown exact alias must be refused")
    registered = request(
        case,
        "POST",
        asset_path(case.account) + "/aliases",
        json={
            "alias": case.alias,
            "mediaGenerationId": case.media,
            "projectId": case.project,
            "kind": case.kind,
        },
    )
    require(registered.status_code == 201, "Fresh owned composite alias registration failed")
    try:
        body = registered.json()
    except ValueError:
        pytest.fail("Alias registration is not JSON", pytrace=False)
    require(
        body.get("alias") == case.alias
        and body.get("nativeMediaGenerationId") == case.media
        and body.get("projectId") == case.project
        and body.get("kind") == case.kind
        and body.get("verified") is True,
        "Alias registration did not preserve exact binding",
    )
    response = request(case, "GET", asset_path(case.alias), params={"source": "google"})
    data = metadata(response)
    require(data.get("mediaGenerationId") == case.alias, "Native GET must preserve exact alias")
    require(
        isinstance(data.get("url"), str)
        and data["url"].startswith("https://flow-content.google/" + case.kind + "/"),
        "Fresh typed native URL is unavailable",
    )


@then("removing only the alias preserves fresh native media access")
def remove_and_verify(case):
    removed = request(case, "DELETE", mapping_path(case))
    require(removed.status_code == 200, "Local alias deletion failed")
    try:
        body = removed.json()
    except ValueError:
        pytest.fail("Local alias deletion is not JSON", pytrace=False)
    require(
        body.get("removed") is True
        and body.get("googleMediaDeleted") is False
        and body.get("scope") == "local-alias",
        "Deletion must remove only the mapping",
    )
    unknown = request(case, "GET", asset_path(case.alias), params={"source": "google"})
    require(unknown.status_code == 404, "Removed exact alias must be unavailable")
    native = metadata(
        request(
            case,
            "GET",
            asset_path(case.media),
            params={
                "source": "google",
                "email": case.account,
                "projectId": case.project,
            },
        )
    )
    require(
        native.get("mediaGenerationId") == case.media, "Original native media must remain readable"
    )
