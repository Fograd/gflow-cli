"""Scoped, validated overrides for the observed ogiZ0b image submit envelope."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode

from gflow_cli.errors import WireFormatError


@dataclass
class ImageOverrides:
    project: str
    count: int
    seed: int | None = None
    token: Callable[[Any], Awaitable[str]] | None = None
    used: bool = False
    metadata_required: bool = True

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


CAPTCHA_METADATA_JS = """
() => {
 const enterprise = window.grecaptcha?.enterprise;
 if (!enterprise || typeof enterprise.execute !== 'function') return false;
 if (window.__gflowOriginalExecute) return true;
 const original = enterprise.execute;
 window.__gflowOriginalExecute = original;
 enterprise.execute = function(key, options) {
   window.__gflowCaptchaMetadata = {sitekey:key, action:options?.action};
   return original.call(this, key, options);
 };
 return true;
}
"""

CLEANUP_CAPTCHA_JS = """
() => {
 if (window.__gflowOriginalExecute && window.grecaptcha?.enterprise)
   window.grecaptcha.enterprise.execute = window.__gflowOriginalExecute;
 delete window.__gflowOriginalExecute;
 delete window.__gflowCaptchaMetadata;
}
"""
