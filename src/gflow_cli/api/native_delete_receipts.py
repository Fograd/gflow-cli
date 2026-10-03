"""Private confirmed-delete receipts; absence alone never proves ownership."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from gflow_cli.api.transports.migrated_projects import parse_projects
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.auth.verification import find_emails


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("Delete receipt directory must be private and regular")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("Delete receipt directory has another owner")


class DeleteReceipts:
    def __init__(self, profile: Path, owner: str, project: str) -> None:
        self.owner = owner
        self.project = validate_identifier(project)
        if len(owner) != 64 or any(c not in "0123456789abcdef" for c in owner):
            raise ValueError("Delete receipt owner scope is unavailable")
        root = profile / ".gflow_delete_receipts"
        _private_directory(root)
        root = root / owner
        _private_directory(root)
        self.root = root / self.project
        _private_directory(self.root)

    def kind(self, identifier: str) -> str | None:
        identifier = validate_identifier(identifier)
        target = self.root / (identifier + ".json")
        try:
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 1024:
                raise ValueError("Delete receipt file is not private bounded metadata")
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ValueError("Delete receipt file has another owner")
            row = json.loads(stream.read(1025))
        if not isinstance(row, dict):
            raise ValueError("Delete receipt does not match the verified scope")
        row = cast(dict[str, Any], row)
        if (
            set(row) != {"version", "owner", "project", "media", "kind"}
            or type(row["version"]) is not int
            or row["version"] != 1
            or row["owner"] != self.owner
            or row["project"] != self.project
            or row["media"] != identifier
            or row["kind"] not in {"image", "video", "audio"}
        ):
            raise ValueError("Delete receipt does not match the verified scope")
        return cast(str, row["kind"])

    def record(self, identifier: str, kind: str) -> None:
        identifier = validate_identifier(identifier)
        if kind not in {"image", "video", "audio"}:
            raise ValueError("Unknown delete receipt media type")
        fd, name = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "version": 1,
                        "owner": self.owner,
                        "project": self.project,
                        "media": identifier,
                        "kind": kind,
                    },
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.root / (identifier + ".json"))
        finally:
            Path(name).unlink(missing_ok=True)


async def verified_delete_receipts(page: Any, profile: Path, project: str) -> DeleteReceipts:
    """Fresh same-session identity plus positive bounded project membership."""
    response = await page.context.request.get("https://myaccount.google.com/u/0/", timeout=15000)
    url = urlsplit(str(response.url))
    if (
        response.status != 200
        or url.scheme != "https"
        or url.netloc != "myaccount.google.com"
        or url.path not in {"/", "/u/0", "/u/0/"}
        or parse_qs(url.query).get("authuser", ["0"]) != ["0"]
    ):
        raise ValueError("Current Google account identity could not be verified")
    body = await response.body()
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("Account identity response exceeded its size budget")
    emails = {email.casefold() for email in find_emails(body.decode("utf-8"))}
    if len(emails) != 1:
        raise ValueError("Current Google account identity is ambiguous")
    owner = hashlib.sha256(next(iter(emails)).encode("utf-8")).hexdigest()
    await page.goto("https://flow.google.com/project/" + project, wait_until="domcontentloaded")
    await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=15000)
    cursor = None
    for _ in range(2):
        result = parse_projects(
            await native_rpc(
                page,
                "UpteDb",
                ["projects/*", 21, cursor, None, None, None, [1]],
                "/u/0/",
                require_single=True,
            )
        )
        if any(row["project_id"] == project for row in result["projects"]):
            return DeleteReceipts(profile, owner, project)
        cursor = result["next_cursor"]
        if cursor is None:
            break
    raise ValueError("Selected project was not positively observed in the bounded account listing")
