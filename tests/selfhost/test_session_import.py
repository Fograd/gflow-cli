"""The parser never starts a browser or reports cookie presence as authentication."""

from __future__ import annotations

import pytest

from gflow_cli.selfhost.session_import import CookieTableError, parse_cookie_table

NOW = 1800000000.0
ROW = (
    "SAPISID\tprivate-test-value\t.google.com\t/\t2030-01-01T00:00:00.000Z\t20\t\t✓\tLax\t\tMedium"
)


def test_headerless_devtools_row_is_typed_and_repr_private() -> None:
    table = parse_cookie_table(ROW, now=NOW)
    assert table.count == 1
    cookie = table.playwright_cookies()[0]
    assert cookie == {
        "name": "SAPISID",
        "value": "private-test-value",
        "domain": ".google.com",
        "path": "/",
        "expires": 1893456000.0,
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }
    assert "private-test-value" not in repr(table)
    assert table.playwright_cookies() is not table.playwright_cookies()


def test_reordered_header_and_session_cookie() -> None:
    table = parse_cookie_table(
        "Value\tName\tDomain\tPath\tExpires / Max-Age\tSecure\tHttpOnly\tSameSite\n"
        "private-test-value\tSID\t.google.com\t/\tSession\ttrue\ttrue\tNone",
        now=NOW,
    )
    cookie = table.playwright_cookies()[0]
    assert "expires" not in cookie
    assert cookie["httpOnly"] is True
    assert cookie["sameSite"] == "None"


@pytest.mark.parametrize(
    "change",
    [
        (".google.com", "evil.google.com.evil.test"),
        (".google.com", ".evil.test"),
        ("2030-01-01T00:00:00.000Z", "2020-01-01T00:00:00Z"),
        ("2030-01-01T00:00:00.000Z", "NaN"),
        ("2030-01-01T00:00:00.000Z", "Infinity"),
        ("2030-01-01T00:00:00.000Z", "2030-01-01T00:00:00"),
        ("\tLax\t", "\tOdd\t"),
        ("\t✓\t", "\tyes-maybe\t"),
        ("\t\tMedium", "\thttps://evil.test\tMedium"),
        ("SAPISID", "__Host-test"),
        ("SAPISID", "bad name"),
        ("\t/\t", "\tnot-a-path\t"),
    ],
)
def test_invalid_fields_have_secret_free_error(change: tuple[str, str]) -> None:
    with pytest.raises(CookieTableError) as error:
        parse_cookie_table(ROW.replace(*change), now=NOW)
    assert "private-test-value" not in str(error.value)
    assert "evil.test" not in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "\n",
        "short\ttable",
        ROW + "\n" + ROW,
        ROW + "\textra",
        "x" * (1024 * 1024 + 1),
        ROW.replace("private-test-value", "x" * 16385),
    ],
)
def test_ambiguous_or_unbounded_tables_rejected(raw: str) -> None:
    with pytest.raises(CookieTableError):
        parse_cookie_table(raw, now=NOW)


def test_nonfinite_now_rejected() -> None:
    with pytest.raises(CookieTableError):
        parse_cookie_table(ROW, now=float("nan"))


def test_distinct_path_and_host_cookie_semantics() -> None:
    rows = (
        ROW
        + "\n"
        + ROW.replace("SAPISID", "__Host-test").replace(".google.com", "accounts.google.com")
    )
    assert parse_cookie_table(rows, now=NOW).count == 2


def test_device_bound_cookie_refused_before_browser() -> None:
    with pytest.raises(CookieTableError, match="device-bound"):
        parse_cookie_table(ROW.replace("SAPISID", "__Secure-1PSIDRTS"), now=NOW)
