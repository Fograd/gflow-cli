"""Exact single-use token rewrite for the measured native 2K image upscale."""

from __future__ import annotations

import json
from contextvars import Context, copy_context
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from gflow_cli.api.native_captcha import native_captcha_submission, validate_native_captcha_token
from gflow_cli.errors import WireFormatError


def rewrite_upscale(body: str, *, project: str, media: str, token: str) -> str:
    """Preserve every form/frame/argument field except the measured CAPTCHA token."""
    validate_native_captcha_token(token)
    try:
        if len(body) > 2 * 1024 * 1024:
            raise ValueError()
        pairs = parse_qsl(body, keep_blank_values=True)
        indexes = [i for i, (key, _) in enumerate(pairs) if key == "f.req"]
        if len(indexes) != 1:
            raise ValueError()
        index = indexes[0]
        frames: Any = json.loads(pairs[index][1])
        if not isinstance(frames, list) or len(cast(list[Any], frames)) != 1:
            raise ValueError()
        if not isinstance(frames[0], list) or len(cast(list[Any], frames)[0]) != 1:
            raise ValueError()
        frame: Any = cast(list[Any], frames)[0][0]
        if not isinstance(frame, list) or len(cast(list[Any], frame)) != 4 or frame[0] != "SPrCad":
            raise ValueError()
        args: Any = json.loads(cast(list[Any], frame)[1])
        if not isinstance(args, list) or len(cast(list[Any], args)) != 3:
            raise ValueError()
        ctx: Any = cast(list[Any], args)[2]
        if (
            args[0] != media
            or type(cast(list[Any], args)[1]) is not int
            or args[1] != 1
            or not isinstance(ctx, list)
            or len(cast(list[Any], ctx)) != 11
            or ctx[5] != project
            or not isinstance(ctx[10], list)
            or len(cast(list[Any], ctx)[10]) != 2
            or type(cast(list[Any], ctx)[10][1]) is not int
            or ctx[10][1] != 1
            or not isinstance(ctx[10][0], str)
            or len(ctx[10][0]) < 20
        ):
            raise ValueError()
        ctx[10][0] = token
        frame[1] = json.dumps(args, separators=(",", ":"))
        pairs[index] = ("f.req", json.dumps(frames, separators=(",", ":")))
        return urlencode(pairs)
    except (ValueError, TypeError, IndexError, KeyError):
        raise WireFormatError(
            detail="Image upscale override refused an unrecognised envelope"
        ) from None


@dataclass
class UpscaleOverride:
    project: str
    media: str
    token: str = field(repr=False)
    used: bool = False
    dispatched: bool = False
    request: Any = field(default=None, repr=False)
    context: Context = field(default_factory=copy_context, repr=False)

    async def guard(self, route: Any, request: Any) -> None:
        """Pass unrelated RPCs; bind acknowledgment to this exact dispatched request."""
        url = urlsplit(str(request.url))
        rpcids = dict(parse_qsl(url.query)).get("rpcids", "").split(",")
        known = "SPrCad" in rpcids
        try:
            raw: Any = json.loads(
                next(v for k, v in parse_qsl(str(request.post_data or "")) if k == "f.req")
            )
            known = known or any(
                isinstance(frame, list)
                and bool(cast(list[Any], frame))
                and cast(list[Any], frame)[0] == "SPrCad"
                for group in cast(list[Any], raw)
                if isinstance(group, list)
                for frame in cast(list[Any], group)
            )
        except (ValueError, TypeError, StopIteration):
            pass
        if not known:
            await route.fallback()
            return
        try:
            if self.used:
                raise WireFormatError(detail="Image upscale override cannot replay")
            if (
                request.method != "POST"
                or url.scheme != "https"
                or url.netloc != "flow.google.com"
                or url.path != "/_/AiSandboxAngularFrontend/data/batchexecute"
            ):
                raise WireFormatError(detail="Image upscale override refused endpoint")
            replacement = rewrite_upscale(
                request.post_data or "", project=self.project, media=self.media, token=self.token
            )
            self.used = True
            self.token = ""
            self.request = request
            self.dispatched = True
            self.context.run(native_captcha_submission)
            await route.continue_(post_data=replacement)
        except BaseException:
            await route.abort()
            raise
