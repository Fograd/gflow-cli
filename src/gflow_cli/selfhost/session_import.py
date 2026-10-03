"""Strict, secret-private useapi-style DevTools cookie table input.

Parsing is not authentication. Browser import must separately verify account
identity and actual Flow access before any profile is registered or activated.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NoReturn, NotRequired, TypedDict, cast

MAX_TABLE_BYTES = 1024 * 1024
MAX_COOKIES = 256
MAX_VALUE_BYTES = 16384
_ALLOWED_DOMAINS = frozenset(
    {
        "google.com",
        ".google.com",
        "accounts.google.com",
        ".accounts.google.com",
        "labs.google",
        ".labs.google",
        "flow.google.com",
        ".flow.google.com",
    }
)
_POSITIONAL = (
    "name",
    "value",
    "domain",
    "path",
    "expires",
    "size",
    "httponly",
    "secure",
    "samesite",
    "partitionkey",
    "priority",
)
_REQUIRED = frozenset(_POSITIONAL[:5])
_COOKIE_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,256}\Z")


class CookieTableError(ValueError):
    """A safe fixed message, never derived from cookie names or values."""


class ImportedCookie(TypedDict):
    name: str
    value: str
    domain: str
    path: str
    expires: NotRequired[float]
    httpOnly: bool
    secure: bool
    sameSite: NotRequired[Literal["Strict", "Lax", "None"]]


@dataclass(frozen=True)
class CookieTable:
    count: int
    _cookies: tuple[ImportedCookie, ...] = field(repr=False)

    def playwright_cookies(self) -> list[ImportedCookie]:
        """Private browser payload; independent copies prevent parser state mutation."""
        return [cookie.copy() for cookie in self._cookies]


def _fail(message: str) -> NoReturn:
    raise CookieTableError(message)


def _flag(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"", "false"}:
        return False
    if normalized in {"true", "✓", "✔"}:
        return True
    _fail("Cookie table has an invalid boolean flag")


def _expiry(value: str, now: float) -> float | None:
    if value.lower() == "session":
        return None
    try:
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
            result = float(value)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                _fail("Cookie expiry must include a timezone")
            result = parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        raise CookieTableError("Cookie table has an invalid expiry") from None
    if not math.isfinite(result) or not now < result <= 253402300799:
        _fail("Cookie expiry is invalid or expired")
    return result


def _header(cell: str) -> str:
    normalized = re.sub(r"[ /_-]", "", cell).lower()
    return "expires" if normalized == "expiresmaxage" else normalized


def _parse_row(cells: list[str], columns: tuple[str, ...], now: float) -> ImportedCookie:
    if len(cells) > len(columns) or len(cells) < len(columns):
        _fail("Cookie table row has an unexpected column count")
    row = dict(zip(columns, cells, strict=True))
    name, value = row["name"], row["value"]
    domain, path = row["domain"].lower(), row["path"]
    if not _COOKIE_NAME.fullmatch(name) or name == "__Secure-1PSIDRTS":
        _fail("Cookie table has an invalid name or a device-bound session")
    if domain not in _ALLOWED_DOMAINS:
        _fail("Cookie domain is not in the Google import allowlist")
    if (
        not path.startswith("/")
        or len(path) > 2048
        or any(ord(c) < 32 or ord(c) == 127 for c in path)
    ):
        _fail("Cookie table has an invalid path")
    if len(value.encode("utf-8")) > MAX_VALUE_BYTES or any(
        ord(c) < 32 or ord(c) == 127 for c in value
    ):
        _fail("Cookie value is invalid or exceeds the limit")
    http_only, secure = _flag(row.get("httponly", "")), _flag(row.get("secure", ""))
    if (name.startswith("__Secure-") and not secure) or (
        name.startswith("__Host-") and (not secure or path != "/" or domain.startswith("."))
    ):
        _fail("Cookie prefix constraints are not satisfied")
    same_site = row.get("samesite", "")
    if same_site not in {"", "Strict", "Lax", "None"} or (same_site == "None" and not secure):
        _fail("Cookie table has invalid SameSite constraints")
    if row.get("partitionkey", ""):
        _fail("Partitioned cookie import is not supported")
    if row.get("priority", "") not in {"", "Low", "Medium", "High"}:
        _fail("Cookie table has an unsupported priority")
    size = row.get("size", "")
    if size and (not size.isascii() or not size.isdigit() or len(size) > 8):
        _fail("Cookie table has an invalid size column")
    cookie: ImportedCookie = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "httpOnly": http_only,
        "secure": secure,
    }
    expires = _expiry(row["expires"], now)
    if expires is not None:
        cookie["expires"] = expires
    if same_site:
        assert same_site in {"Strict", "Lax", "None"}
        cookie["sameSite"] = cast('Literal["Strict", "Lax", "None"]', same_site)
    return cookie


def parse_cookie_table(raw: object, *, now: float | None = None) -> CookieTable:
    """Parse headerless five-to-eleven columns or an explicit supported header.

    Empty SameSite means unspecified. Session cookies omit expires; ISO dates
    require a timezone, numeric dates are absolute Unix seconds. Ambiguous columns,
    unsupported partitioning and duplicate identities are refused before a browser.
    """
    if not isinstance(raw, str):
        _fail("cookies must be a DevTools table string")
    assert isinstance(raw, str)
    try:
        table_size = len(raw.encode("utf-8"))
    except UnicodeEncodeError:
        raise CookieTableError("Cookie table has invalid text encoding") from None
    if not 1 <= table_size <= MAX_TABLE_BYTES:
        _fail("Cookie table is empty or exceeds 1 MiB")
    current = time.time() if now is None else now
    if isinstance(current, bool) or not math.isfinite(current):
        _fail("Cookie verification time is invalid")
    lines = raw.splitlines()
    if not lines or len(lines) > MAX_COOKIES + 1 or any(not line for line in lines):
        _fail("Cookie table has empty rows or exceeds 256 cookies")
    cells = [line.split("\t") for line in lines]
    first = cells[0]
    possible_header = tuple(_header(cell) for cell in first)
    if "name" in possible_header and "value" in possible_header:
        if (
            not _REQUIRED.issubset(possible_header)
            or len(set(possible_header)) != len(possible_header)
            or any(column not in _POSITIONAL for column in possible_header)
        ):
            _fail("Cookie table has an unsupported or incomplete header")
        columns = possible_header
        cells = cells[1:]
    else:
        if not 5 <= len(first) <= len(_POSITIONAL):
            _fail("Cookie table requires five to eleven columns")
        columns = _POSITIONAL[: len(first)]
    if not 1 <= len(cells) <= MAX_COOKIES:
        _fail("Cookie table requires one to 256 cookies")
    cookies: list[ImportedCookie] = []
    seen: set[tuple[str, str, str]] = set()
    for values in cells:
        cookie = _parse_row(values, columns, float(current))
        identity = (cookie["name"], cookie["domain"], cookie["path"])
        if identity in seen:
            _fail("Cookie table contains duplicate identities")
        seen.add(identity)
        cookies.append(cookie)
    return CookieTable(count=len(cookies), _cookies=tuple(cookies))
