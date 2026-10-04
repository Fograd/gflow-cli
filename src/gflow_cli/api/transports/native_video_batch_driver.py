"""Current UI batch submission with all actual acknowledgments retained."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, copy_context
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote_plus, urlsplit

from gflow_cli.api.transports.batchexecute import parse_frames, rpc_reply_frame_count
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.api.transports.native_asset_download import download_asset
from gflow_cli.api.transports.native_asset_lookup import existing_asset
from gflow_cli.api.transports.native_video_batch_codec import (
    VIDEO_RPCS,
    BatchRequest,
    batch_ack,
    batch_request,
    known_batch_pairs,
)
from gflow_cli.api.video import (
    VideoBatchResult,
    VideoResult,
    VideoStarted,
    VideoStartedCallback,
    VideoStatus,
)
from gflow_cli.errors import (
    ContentPolicyError,
    NativeQuotaError,
    NativeUIVideoBatchUnknownError,
    WafRejectionError,
    WireFormatError,
)

# Free source-proof hook: invoked after exact request validation, before forwarding.
batch_submit_probe: ContextVar[Callable[[BatchRequest], None] | None] = ContextVar(
    "batch_submit_probe", default=None
)


def _at(value: Any, *indices: int) -> Any:
    for index in indices:
        if not isinstance(value, list) or len(cast(list[Any], value)) <= index:
            return None
        value = cast(list[Any], value)[index]
    return value


async def submit_batch(
    page: Any,
    composer: Any,
    *,
    project: str,
    count: int,
    rpcid: str,
    timeout: float,
    start: str | None,
    end: str | None,
    references: tuple[str, ...],
    characters: tuple[str, ...],
    on_dispatch: Callable[[], None] | None,
    on_known: Callable[[tuple[tuple[str, str], ...]], Awaitable[None]] | None,
) -> tuple[tuple[str, str], ...]:
    from gflow_cli.api.transports.migrated_composer import (  # pyright: ignore[reportPrivateUsage]
        _ligature,  # pyright: ignore[reportPrivateUsage]
        _submit_refusal,  # pyright: ignore[reportPrivateUsage]
    )
    from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides

    override = active_video_overrides.get()
    if override is not None:
        if override.project != project or override.count != count or override.closed:
            raise WireFormatError(detail="Batch CAPTCHA scope differs from selected outputs")
        override.capture_metadata(page)
    context = copy_context()
    loop = asyncio.get_running_loop()
    result: asyncio.Future[tuple[tuple[str, str], ...]] = loop.create_future()
    contract: BatchRequest | None = None
    dispatched: Any = None
    known: list[tuple[str, str]] = []
    closed = False
    primary_error: BaseException | None = None
    pattern = "**/batchexecute*"

    async def guard(route: Any, request: Any) -> None:
        nonlocal contract, dispatched
        body = request.post_data or ""
        # The positively known submit RPC is named in f.req, sometimes without rpcids.
        try:
            from gflow_cli.api.transports.migrated_composer import (  # pyright: ignore[reportPrivateUsage]
                _body_rpcid,  # pyright: ignore[reportPrivateUsage]
                _rpcid,  # pyright: ignore[reportPrivateUsage]
            )

            actual = _body_rpcid(unquote_plus(body)) or _rpcid(request.url)
            if actual not in VIDEO_RPCS:
                await route.fallback()
                return
            parsed = urlsplit(str(request.url))
            if (
                closed
                or dispatched is not None
                or request.method != "POST"
                or parsed.scheme != "https"
                or parsed.netloc != "flow.google.com"
                or parsed.path != "/_/AiSandboxAngularFrontend/data/batchexecute"
            ):
                raise WireFormatError(detail="Native batch requires one exact official submit")
            contract = batch_request(
                body,
                project_id=project,
                count=count,
                rpcid=rpcid,
                start_media_id=start,
                end_media_id=end,
                reference_ids=references,
                character_ids=characters,
            )
            probe = context.get(batch_submit_probe)
            if probe is not None:
                probe(contract)
            replacement = await override.apply(page, body) if override is not None else None
            if on_dispatch is not None:
                on_dispatch()
            dispatched = request
            if override is not None:
                override.dispatched = True
                override.request = request
                override.rpcid = rpcid
                if override.observe is not None:
                    override.context.run(override.observe, "submitted")
                await route.continue_(post_data=replacement)
            else:
                await route.continue_()
        except Exception as exc:
            await route.abort()
            if dispatched is None:
                exc.add_note("Native batch request aborted before forwarding")
            if not result.done():
                result.set_exception(exc)

    async def response(value: Any) -> None:
        if closed or dispatched is None or value.request is not dispatched or result.done():
            return
        try:
            text = await value.text()
            if closed or result.done():
                return
            frames = [payload for rid, payload in parse_frames(text) if rid == rpcid]
            for payload in frames:
                for pair in known_batch_pairs(payload, project):
                    if pair not in known and len(known) < 4:
                        known.append(pair)
            if override is not None:
                override.known_media_ids[:] = [media for media, _ in known]
                override.known_workflow_ids[:] = [workflow for _, workflow in known]
            if on_known is not None and known:
                await on_known(tuple(known))
            if rpc_reply_frame_count(text, rpcid) != 1:
                raise WireFormatError(detail="Native batch requires one unambiguous reply")
            refusal = _submit_refusal(text, (rpcid,))
            if refusal is not None:
                if known:
                    raise WireFormatError(
                        detail="Native batch refusal also contains actual handles"
                    )
                if override is not None:
                    override.outcome("rejected")
                raise refusal
            if contract is None or len(frames) != 1:
                raise WireFormatError(detail="Native batch reply has no exact request")
            acknowledged = batch_ack(frames[0], contract)
            if override is not None:
                override.outcome("accepted")
            result.set_result(acknowledged)
        except Exception as exc:
            if not result.done():
                result.set_exception(exc)

    page.on("response", response)
    try:
        await page.route(pattern, guard)
        submit = page.locator("button").filter(has=_ligature(page, "arrow_forward")).first
        if not await submit.count() or not await submit.is_enabled():
            raise WireFormatError(detail="Native batch submit button is unavailable")
        await composer._click(page, submit, named="native video batch submit", timeout=5000)
        return await asyncio.wait_for(asyncio.shield(result), min(timeout, 60))
    except BaseException as exc:
        primary_error = exc
        if dispatched is not None:
            if (
                isinstance(exc, (NativeQuotaError, ContentPolicyError, WafRejectionError))
                and not known
            ):
                raise
            if isinstance(exc, asyncio.CancelledError):
                exc.add_note("Native video batch was submitted; never automatically replay")
                raise
            raise NativeUIVideoBatchUnknownError(
                project_id=project,
                media_ids=tuple(m for m, _ in known),
                workflow_ids=tuple(w for _, w in known),
                phase="video_submit",
            ) from None
        raise
    finally:
        closed = True
        if override is not None:
            override.stop_capture(page)
        cleanup_error: BaseException | None = None
        try:
            await page.unroute(pattern, guard)
        except BaseException as exc:
            cleanup_error = exc
        finally:
            page.remove_listener("response", response)
            if result.done() and not result.cancelled():
                result.exception()
            elif not result.done():
                result.cancel()
        if cleanup_error is not None and primary_error is None:
            if isinstance(cleanup_error, asyncio.CancelledError):
                cleanup_error.add_note("Native batch acknowledgment exists; never replay")
                raise cleanup_error
            raise NativeUIVideoBatchUnknownError(
                project_id=project,
                media_ids=tuple(m for m, _ in known),
                workflow_ids=tuple(w for _, w in known),
                phase="video_submit",
            ) from None


async def finish_batch(
    page: Any,
    pairs: tuple[tuple[str, str], ...],
    *,
    project: str,
    out_dir: Path | None,
    deadline: float,
    download: bool,
    on_started: VideoStartedCallback | None,
) -> VideoBatchResult:
    results: list[VideoResult] = []
    try:
        for media, workflow in pairs:
            if on_started is not None:
                maybe = on_started(
                    VideoStarted(
                        media_id=media,
                        project_id=project,
                        flow_operation_id=workflow,
                        workflow_id=workflow,
                    )
                )
                if asyncio.iscoroutine(maybe):
                    await maybe
        for media, workflow in pairs:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                remaining = deadline - time.monotonic()
                payload = await asyncio.wait_for(
                    native_rpc(page, "as29s", [media], f"/project/{project}", require_single=True),
                    remaining,
                )
                if not isinstance(payload, list) or payload[:3] != [media, project, workflow]:
                    raise WireFormatError(
                        detail="Native video poll has different actual identities"
                    )
                state = _at(payload, 5, 8, 0)
                if type(state) is not int or state not in (2, 3, 4, 5, 6, 7):
                    raise WireFormatError(detail="Native video poll status is unresolved")
                if state == 3 and _at(payload, 7, 0, 8):
                    asset = existing_asset(
                        payload,
                        project_id=project,
                        media_id=media,
                        workflow_id=workflow,
                        kind="video",
                    )
                    local = None
                    if download:
                        downloaded = await asyncio.wait_for(
                            download_asset(asset, out_dir=out_dir or Path.cwd()),
                            max(0.001, deadline - time.monotonic()),
                        )
                        local = downloaded.path
                    results.append(
                        VideoResult(
                            VideoStatus(
                                media_id=media, status="MEDIA_GENERATION_STATUS_SUCCESSFUL"
                            ),
                            local,
                            project,
                            workflow,
                            workflow,
                        )
                    )
                    break
                if state in (4, 5, 7):
                    results.append(
                        VideoResult(
                            VideoStatus(media_id=media, status="MEDIA_GENERATION_STATUS_FAILED"),
                            None,
                            project,
                            workflow,
                            workflow,
                        )
                    )
                    break
                await asyncio.sleep(min(2, max(0.001, deadline - time.monotonic())))
        return VideoBatchResult(tuple(results), project)
    except asyncio.CancelledError:
        raise
    except Exception:
        raise NativeUIVideoBatchUnknownError(
            project_id=project,
            media_ids=tuple(m for m, _ in pairs),
            workflow_ids=tuple(w for _, w in pairs),
            phase="video_poll",
        ) from None
