"""All-output UI video service; current native field4 codec, no submit replay."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from gflow_cli.api.transports.migrated_composer import (
    _prepare_native_video,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_video_overrides import active_video_overrides
from gflow_cli.api.transports.native_video_batch_driver import finish_batch, submit_batch
from gflow_cli.api.video import (
    GenerateVideoRequest,
    Mode,
    VideoBatchResult,
    VideoStarted,
    VideoStartedCallback,
)
from gflow_cli.errors import ConfigurationError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.dto import GenerationCheckpointObserver


async def generate_video_batch(
    client: FlowApiClient,
    *,
    req: GenerateVideoRequest,
    project_id: str | None = None,
    out_dir: Path | None = None,
    poll_timeout_s: float = 600,
    download: bool = True,
    on_started: VideoStartedCallback | None = None,
    on_checkpoint: GenerationCheckpointObserver | None = None,
) -> VideoBatchResult:
    if type(req.count) is not int or not 2 <= req.count <= 4:
        raise ConfigurationError(detail="Native video batch requires two through four outputs")
    if req.seed is not None:
        raise ConfigurationError(detail="Numeric video seed has no verified UI batch support")
    override = active_video_overrides.get()
    if override is not None and (override.count != req.count or override.project != project_id):
        raise ConfigurationError(detail="Video batch CAPTCHA scope differs from the request")
    if client.transport is None:
        raise RuntimeError("Native video batch requires an opened client")
    if project_id is None:
        project_id = (await client.create_project()).project_id
    try:
        project_id = str(UUID(project_id))
    except (ValueError, TypeError):
        raise ConfigurationError(detail="Native video batch requires a project UUID") from None
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        from urllib.parse import urlsplit

        from gflow_cli.api.dto import GenerationCheckpoint

        if urlsplit(page.url).hostname != "flow.google.com":
            raise ConfigurationError(detail="Native video batch requires flow.google.com")
        composer, pid, start, end, refs = await _prepare_native_video(page, req, project_id)
        rpc = (
            "MZZa6b"
            if req.mode is Mode.R2V
            else "nprQif"
            if req.end_image is not None
            else "eb1hJf"
            if req.mode is Mode.I2V
            else "YhhmEf"
        )
        deadline = time.monotonic() + poll_timeout_s

        def dispatch() -> None:
            if on_checkpoint is not None:
                on_checkpoint(GenerationCheckpoint(phase="submit_attempted"))

        delivered: set[str] = set()

        async def known(pairs: tuple[tuple[str, str], ...]) -> None:
            if on_checkpoint is not None:
                on_checkpoint(
                    GenerationCheckpoint(
                        phase="remote_started",
                        media_ids=tuple(media for media, _ in pairs),
                        workflow_ids=tuple(workflow for _, workflow in pairs),
                    )
                )
            for media, workflow in pairs:
                if media in delivered:
                    continue
                delivered.add(media)
                if on_started is not None:
                    value = on_started(
                        VideoStarted(
                            media_id=media,
                            project_id=pid,
                            flow_operation_id=workflow,
                            workflow_id=workflow,
                        )
                    )
                    if value is not None:
                        await value

        pairs = await submit_batch(
            page,
            composer,
            project=pid,
            count=req.count,
            rpcid=rpc,
            timeout=poll_timeout_s,
            start=start,
            end=end,
            references=refs,
            characters=tuple(req.reference_entities),
            on_dispatch=dispatch,
            on_known=known,
        )
        return await finish_batch(
            page,
            pairs,
            project=pid,
            out_dir=out_dir,
            deadline=deadline,
            download=download,
            on_started=None,
        )
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
