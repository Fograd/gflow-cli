"""Scoped, validated overrides for the observed ogiZ0b image submit envelope."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import Awaitable, Callable, Generator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from gflow_cli.errors import WireFormatError


@dataclass
class ImageOverrides:
    project: str
    count: int
    seed: int | None = None
    token: Callable[[Any], Awaitable[str]] | None = None
    used: bool = False
    metadata_required: bool = True
    metadata: dict[str, str] | None = None
    observer: Callable[[Any], None] | None = field(default=None, repr=False)

    def capture_metadata(self, page: Any) -> None:
        if not self.metadata_required or self.token is None or self.observer is not None:
            return

        def observe(request: Any) -> None:
            try:
                metadata = reload_metadata(str(request.url), request.post_data_buffer or b"")
            except (ValueError, TypeError, AttributeError):
                return
            if metadata is not None:
                self.metadata = metadata

        self.observer = observe
        page.on("request", observe)

    def stop_capture(self, page: Any) -> None:
        if self.observer is not None:
            page.remove_listener("request", self.observer)
            self.observer = None

    async def apply(self, page: Any, body: str) -> str:
        if self.used:
            raise WireFormatError(detail="Image overrides cannot replay a submitted request")
        replacement = await asyncio.wait_for(self.token(page), timeout=110) if self.token else None
        result = rewrite_submit(
            body, project=self.project, count=self.count, seed=self.seed, token=replacement
        )
        self.used = True
        return result


active_overrides: ContextVar[ImageOverrides | None] = ContextVar("image_overrides", default=None)


def rewrite_submit(
    body: str, *, project: str, count: int, seed: int | None = None, token: str | None = None
) -> str:
    """Change only the captured seed/token slots after validating project and shape.

    Measured 2026-10-02 with an aborted image request. A batch uses seed+index;
    original browser tokens must agree in the top-level and per-output context.
    """
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 2147483647 - count + 1):
        raise ValueError("seed must fit the supported signed 32-bit batch range")
    if token is not None and not 20 <= len(token) <= 20000:
        raise ValueError("Invalid supplied CAPTCHA token")
    try:
        pairs = parse_qsl(body, keep_blank_values=True)
        indexes = [i for i, (key, _) in enumerate(pairs) if key == "f.req"]
        if len(indexes) != 1:
            raise ValueError()
        index = indexes[0]
        frames: Any = json.loads(pairs[index][1])
        if len(frames) != 1 or len(frames[0]) != 1 or frames[0][0][0] != "ogiZ0b":
            raise ValueError()
        args: Any = json.loads(frames[0][0][1])
        rows: Any = args[1]
        context: Any = args[3]
        if (
            not isinstance(rows, list)
            or len(cast(list[Any], rows)) != count
            or context[5] != project
        ):
            raise ValueError()
        original = context[10][0]
        if not isinstance(original, str) or len(original) < 20:
            raise ValueError()
        for i, row in enumerate(cast(list[Any], rows)):
            if row[7][5] != project or row[7][10][0] != original or type(row[3]) is not int:
                raise ValueError()
            if seed is not None:
                row[3] = seed + i
            if token is not None:
                row[7][10][0] = token
        if token is not None:
            context[10][0] = token
        frames[0][0][1] = json.dumps(args, separators=(",", ":"))
        pairs[index] = ("f.req", json.dumps(frames, separators=(",", ":")))
        return urlencode(pairs)
    except (ValueError, TypeError, KeyError, IndexError):
        raise WireFormatError(
            detail="Image override refused an unrecognised submit envelope"
        ) from None


def reload_metadata(url: str, body: bytes) -> dict[str, str] | None:
    """Read measured public metadata, never retain the private reload envelope.

    Two aborted image submits on 2026-10-02 observed protobuf field8 action and
    field14 sitekey. The latter must match the trusted request's public k query.
    Unknown or truncated envelopes refuse solver tasks rather than invent an action.
    """
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ("www.google.com", "www.recaptcha.net")
        or parsed.path != "/recaptcha/enterprise/reload"
    ):
        return None
    keys = [value for name, value in parse_qsl(parsed.query) if name == "k"]
    if len(keys) != 1 or not 20 <= len(keys[0]) <= 100 or not 1 <= len(body) <= 65536:
        raise ValueError("Invalid CAPTCHA metadata envelope")
    position = 0

    def varint() -> int:
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(body):
                raise ValueError("Truncated CAPTCHA metadata envelope")
            octet = body[position]
            position += 1
            value |= (octet & 127) << shift
            if octet < 128:
                return value
        raise ValueError("Invalid CAPTCHA metadata varint")

    fields: dict[int, bytes] = {}
    count = 0
    while position < len(body):
        count += 1
        if count > 128:
            raise ValueError("Too many CAPTCHA metadata fields")
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("Invalid CAPTCHA metadata tag")
        if wire == 2:
            length = varint()
            end = position + length
            if end > len(body):
                raise ValueError("Truncated CAPTCHA metadata field")
            if number in (8, 14):
                if number in fields:
                    raise ValueError("Duplicate CAPTCHA metadata field")
                fields[number] = body[position:end]
            position = end
        elif wire == 0:
            varint()
        elif wire in (1, 5):
            position += 8 if wire == 1 else 4
            if position > len(body):
                raise ValueError("Truncated CAPTCHA metadata field")
        else:
            raise ValueError("Unrecognised CAPTCHA metadata wire")
    try:
        action = fields[8].decode("ascii")
        sitekey = fields[14].decode("ascii")
    except (KeyError, UnicodeError):
        raise ValueError("Missing CAPTCHA metadata fields") from None
    if (
        action != "IMAGE_GENERATION"
        or sitekey != keys[0]
        or not re.fullmatch(r"[A-Za-z0-9_-]+", sitekey)
    ):
        raise ValueError("CAPTCHA metadata does not match the measured image action")
    return {"sitekey": sitekey, "action": action}


@contextlib.contextmanager
def image_seed_scope(project: str, count: int, seed: int) -> Generator[ImageOverrides]:
    """Preserve provider callbacks and one-shot state across SDK retry attempts."""
    current = active_overrides.get()
    if current is not None:
        if current.project != project or current.count != count or current.seed not in (None, seed):
            raise ValueError("Image seed conflicts with the active native override")
        original = current.seed
        current.seed = seed
        try:
            yield current
        finally:
            current.seed = original
    else:
        override = ImageOverrides(project=project, count=count, seed=seed)
        state = active_overrides.set(override)
        try:
            yield override
        finally:
            active_overrides.reset(state)
