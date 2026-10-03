"""Portable direct native-media service shared by public adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.native_media import propagate_after_ack
from gflow_cli.config import get_settings

if TYPE_CHECKING:
    from pathlib import Path


async def upload_private_snapshot(profile: str, project: str, private: Path) -> dict[str, Any]:
    settings = get_settings()
    outcome: dict[str, Any] = {}
    primary: BaseException | None = None
    try:
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(profile), headless=settings.headless
        ) as client:
            try:
                outcome.update(await client._upload_native_video_snapshot(project, private))  # pyright: ignore[reportPrivateUsage]
            except BaseException as error:
                primary = error
                raise
    except BaseException as error:
        if primary is not None:
            raise primary from None
        if outcome.get("media_id"):
            propagate_after_ack(
                error, project=project, operation="upload", known=(outcome["media_id"],)
            )
        raise
    return outcome


async def archive_media(profile: str, project: str, identifiers: tuple[str, ...]) -> dict[str, Any]:
    settings = get_settings()
    outcome: dict[str, Any] = {}
    primary: BaseException | None = None
    try:
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(profile), headless=settings.headless
        ) as client:
            try:
                outcome.update(
                    await client.archive_native_media(
                        project_id=project, media_ids=identifiers, confirm_archive=True
                    )
                )
            except BaseException as error:
                primary = error
                raise
    except BaseException as error:
        if primary is not None:
            raise primary from None
        known = tuple(outcome.get("archived_media_ids", []))
        if known:
            propagate_after_ack(
                error,
                project=project,
                operation="archive",
                known=known,
                pending=tuple(item for item in identifiers if item not in known),
            )
        raise
    return outcome
