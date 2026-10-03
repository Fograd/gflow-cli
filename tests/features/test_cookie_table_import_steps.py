"""Offline BDD for the credential parsing boundary."""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.selfhost.session_import import CookieTableError, parse_cookie_table

scenarios("cookie_table_import.feature")


@pytest.fixture
def case():
    return {}


@given("a bounded session cookie table")
def valid_table(case):
    case["raw"] = "SID\tprivate-test-value\t.google.com\t/\tSession"


@given("a duplicate cookie table")
def duplicate_table(case):
    row = "SID\tprivate-test-value\t.google.com\t/\tSession"
    case["raw"] = row + "\n" + row


@when("the cookie table is parsed")
def parse(case):
    try:
        case["table"] = parse_cookie_table(case["raw"])
    except CookieTableError as exc:
        case["error"] = str(exc)


@then("the private browser input contains one cookie")
def private_input(case):
    assert case["table"].playwright_cookies()[0]["value"] == "private-test-value"
    assert case["table"].count == 1


@then("the public representation contains neither its value nor a health claim")
def no_authentication_claim(case):
    public = repr(case["table"])
    assert "private-test-value" not in public
    assert "authenticated" not in public
    assert "health" not in public


@then("validation fails with a safe message")
def safe_failure(case):
    assert "error" in case
    assert "private-test-value" not in case["error"]
    assert "table" not in case
