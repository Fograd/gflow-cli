"""Single-use CAPTCHA replacement for source-backed native video RPC envelopes."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from contextvars import Context, ContextVar, copy_context
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

from gflow_cli.api.transports.migrated_image_overrides import reload_metadata
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import WireFormatError

VIDEO_SUBMIT_RPCS = frozenset(("YhhmEf", "eb1hJf", "nprQif", "MZZa6b"))


def _envelope(body: str, project: str, count: int) -> tuple[list[tuple[str, str]], int, Any, Any]:
    try:
        if len(body) > 2 * 1024 * 1024:
            raise ValueError()
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError()
        pairs = parse_qsl(body, keep_blank_values=True)
        indexes = [i for i, (key, _) in enumerate(pairs) if key == "f.req"]
        if len(indexes) != 1:
            raise ValueError()
        index = indexes[0]
        frames: Any = json.loads(pairs[index][1])
        if (
            not isinstance(frames, list)
            or len(cast(list[Any], frames)) != 1
            or not isinstance(frames[0], list)
            or len(cast(list[Any], frames)[0]) != 1
            or cast(list[Any], frames)[0][0][0] not in VIDEO_SUBMIT_RPCS
        ):
            raise ValueError()
        args: Any = json.loads(cast(list[Any], frames)[0][0][1])
        if not isinstance(args, list) or len(cast(list[Any], args)) != 3:
            raise ValueError()
        rows: Any = cast(list[Any], args)[0]
        context: Any = cast(list[Any], args)[1]
        if (
            not isinstance(rows, list)
            or len(cast(list[Any], rows)) != count
            or not all(
                isinstance(row, list) and bool(cast(list[Any], row))
                for row in cast(list[Any], rows)
            )
            or not isinstance(context, list)
            or context[5] != project
            or not isinstance(context[10], list)
            or len(cast(list[Any], context)[10]) != 2
            or type(cast(list[Any], context)[10][1]) is not int
            or context[10][1] != 1
            or not isinstance(context[10][0], str)
            or len(context[10][0]) < 20
        ):
            raise ValueError()
        return pairs, index, cast(Any, frames), cast(Any, args)
    except (ValueError, TypeError, KeyError, IndexError):
        raise WireFormatError(
            detail="Video override refused an unrecognised submit envelope"
        ) from None


def rewrite_submit(body: str, *, project: str, count: int, token: str) -> str:
    """Replace only context CAPTCHA field11 token after exact frame checks."""
    if not 20 <= len(token) <= 20000:
        raise WireFormatError(detail="Invalid supplied video CAPTCHA token")
    pairs, index, frames, args = _envelope(body, project, count)
    args[1][10][0] = token
    frames[0][0][1] = json.dumps(args, separators=(",", ":"))
    pairs[index] = ("f.req", json.dumps(frames, separators=(",", ":")))
    return urlencode(pairs)


@dataclass
class VideoOverrides:
    project: str
    count: int
    token: Callable[[Any], Awaitable[str]] = field(repr=False)
    used: bool = False
    dispatched: bool = False
    on_validated: Callable[[str], None] | None = field(default=None, repr=False)
    closed: bool = False
    terminal: str | None = None
    request: Any = field(default=None, repr=False)
    rpcid: str | None = None
    known_media_ids: list[str] = field(default_factory=lambda: list[str](), repr=False)
    known_workflow_ids: list[str] = field(default_factory=lambda: list[str](), repr=False)
    context: Context = field(default_factory=copy_context, repr=False)
    observe: Callable[[str], None] | None = field(default=None, repr=False)
    provider_name: str | None = None
    metadata_required: bool = False
    metadata: dict[str, str] | None = None
    metadata_url: str | None = None
    metadata_at: float = 0
    observer: Callable[[Any], None] | None = field(default=None, repr=False)
    previous_request_ids: set[str] | None = field(default=None, repr=False)

    def page_matches(self, page: Any) -> bool:
        url = urlsplit(str(getattr(page, "url", "")))
        return (
            url.scheme == "https"
            and url.netloc == "flow.google.com"
            and url.path.rstrip("/") == "/project/" + self.project
        )

    def capture_metadata(self, page: Any) -> None:
        if not self.metadata_required or self.observer is not None:
            return

        def observe(request: Any) -> None:
            if str(request.method) != "POST":
                return
            try:
                metadata = reload_metadata(
                    str(request.url),
                    request.post_data_buffer or b"",
                    expected_action="VIDEO_GENERATION",
                )
            except (ValueError, TypeError, AttributeError):
                return
            if (
                metadata is not None
                and not self.closed
                and not self.used
                and self.page_matches(page)
            ):
                self.metadata = metadata
                self.metadata_url = str(page.url)
                self.metadata_at = time.monotonic()

        self.observer = observe
        page.on("request", observe)

    def stop_capture(self, page: Any) -> None:
        if self.observer is not None:
            page.remove_listener("request", self.observer)
            self.observer = None

    def outcome(self, value: str) -> None:
        if self.closed or not self.dispatched or self.terminal is not None:
            return
        self.terminal = value
        if self.observe is not None:
            self.context.run(self.observe, value)

    def close(self) -> None:
        self.outcome("unknown")
        self.closed = True
        self.metadata = None

    async def apply(self, page: Any, body: str) -> str:
        if self.closed or self.used:
            raise WireFormatError(detail="Video overrides cannot replay a submitted request")
        _, _, frames, args = _envelope(body, self.project, self.count)
        if self.previous_request_ids is not None:
            if self.count != 1:
                raise WireFormatError(detail="Provider video CAPTCHA requires count one")
            rpcid = frames[0][0][0]
            index = {"YhhmEf": 4, "eb1hJf": 5, "nprQif": 6, "MZZa6b": 5}[rpcid]
            try:
                requested_id: Any = args[0][0][index][4]
            except (IndexError, TypeError):
                raise WireFormatError(
                    detail="Fresh native requested video identity is missing"
                ) from None
            if not is_uuid(requested_id):
                raise WireFormatError(detail="Native video requested identity is invalid")
            requested_id = str(UUID(requested_id))
            if requested_id in self.previous_request_ids:
                raise WireFormatError(detail="Native video attempt cannot reuse requested identity")
            self.previous_request_ids.add(requested_id)
        if self.on_validated is not None:
            self.on_validated(body)
        # Mark before awaiting: concurrent callbacks must never spend one token twice.
        self.used = True
        replacement = await asyncio.wait_for(
            self.token(page), timeout=260 if self.metadata_required else 110
        )
        if self.closed:
            raise WireFormatError(detail="Video override scope closed during token consumption")
        return rewrite_submit(body, project=self.project, count=self.count, token=replacement)


active_video_overrides: ContextVar[VideoOverrides | None] = ContextVar(
    "video_overrides", default=None
)


async def guard_video_submit(route: Any, request: Any, page: Any, override: VideoOverrides) -> None:
    """Pass unrelated RPCs; abort unsafe video bodies before Google dispatch."""
    body = request.post_data or ""
    try:
        pairs = parse_qsl(body, keep_blank_values=True)
        frames: Any = json.loads(next(value for key, value in pairs if key == "f.req"))
        known = any(
            isinstance(frame, list)
            and bool(cast(list[Any], frame))
            and cast(list[Any], frame)[0] in VIDEO_SUBMIT_RPCS
            for group in cast(list[Any], frames)
            if isinstance(group, list)
            for frame in cast(list[Any], group)
        )
    except (ValueError, TypeError, StopIteration):
        # A URL naming a submit must not escape validation through a bad body.
        known = any(
            value in VIDEO_SUBMIT_RPCS
            for key, value in parse_qsl(urlsplit(str(request.url)).query)
            if key == "rpcids"
        )
    if not known:
        await route.fallback()
        return
    url = urlsplit(str(request.url))
    if (
        url.scheme != "https"
        or url.netloc != "flow.google.com"
        or url.path != "/_/AiSandboxAngularFrontend/data/batchexecute"
        or str(request.method) != "POST"
    ):
        raise WireFormatError(
            detail="Video CAPTCHA override requires the native Google RPC endpoint"
        )
    rewritten = await override.apply(page, body)
    _, _, frames, _ = _envelope(rewritten, override.project, override.count)
    override.rpcid = frames[0][0][0]
    override.request = request
    override.dispatched = True
    if override.observe is not None:
        override.context.run(override.observe, "submitted")
    await route.continue_(post_data=rewritten)


def acknowledgement_allowed(override: VideoOverrides, project: object) -> bool:
    """Never adopt output handles before this guarded submit or for another project."""
    return not override.closed and override.dispatched and project == override.project
