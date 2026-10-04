"""Fresh current-user native People read; no bootstrap or local identity adoption."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit
from uuid import UUID

from gflow_cli.api.transports.migrated_rpc import native_rpc

if TYPE_CHECKING:
    from playwright.async_api import Page

_IDENTITY_EMAIL = re.compile(r'[^\s"<>]{1,128}@[^\s"<>]{1,125}')


def native_identity_args() -> list[Any]:
    """Primary USER_PROFILE builder: me plus its exact People field/source mask."""
    return [
        ["me"],
        [[["person.photo", "person.name", "person.email", "person.metadata"]], None, [1, 7, 10]],
    ]


def _list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Native current principal is unavailable")
    return cast(list[Any], value)


def parse_native_identity(payload: object) -> str:
    """Require one self lookup and one usable current email; do not choose among aliases."""
    try:
        top = _list(payload)
        lookups = _list(top[0])
        if len(lookups) != 1:
            raise ValueError()
        lookup = _list(lookups[0])
        if len(lookup) < 3 or lookup[0] != "me":
            raise ValueError()
        status = lookup[1]
        if type(status) is not int or status != 1:
            raise ValueError()
        person = _list(lookup[2])
        emails = _list(person[9])
        if len(emails) != 1:
            raise ValueError()
        record = _list(emails[0])
        email = record[1]
        if not isinstance(email, str) or _IDENTITY_EMAIL.fullmatch(email) is None:
            raise ValueError()
        return email
    except (IndexError, ValueError, TypeError):
        raise ValueError("Native current principal is unavailable") from None


def _trusted_origin(page: Page) -> bool:
    parsed = urlsplit(str(page.url))
    return parsed.scheme == "https" and parsed.netloc == "flow.google.com"


async def read_native_identity(page: Page) -> str:
    """One bounded official singleton GetPeople read, bound to the live Flow origin."""
    if not _trusted_origin(page):
        raise ValueError("Native current principal is unavailable")
    source_path = "/u/0/"
    path = urlsplit(str(page.url)).path
    if path.startswith("/project/"):
        project = path.removeprefix("/project/").rstrip("/")
        try:
            UUID(project)
        except ValueError:
            raise ValueError("Native current principal is unavailable") from None
        source_path = f"/project/{project}"
    payload = await asyncio.wait_for(
        native_rpc(page, "o30O0e", native_identity_args(), source_path, require_single=True),
        timeout=30,
    )
    if not _trusted_origin(page):
        raise ValueError("Native current principal is unavailable")
    return parse_native_identity(payload)
