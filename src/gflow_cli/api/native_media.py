"""Direct native media mutations; never retry uncertain writes."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from gflow_cli.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path

    from gflow_cli.api.client import FlowApiClient


def validate_project(project: object) -> str:
    if not isinstance(project, str):
        raise ConfigurationError(detail="Native project identifier must be a UUID")
    try:
        return str(UUID(project))
    except ValueError:
        raise ConfigurationError(detail="Native project identifier must be a UUID") from None


def validate_upload(project: object, rights_confirmed: object) -> str:
    if rights_confirmed is not True:
        raise ConfigurationError(detail="Explicit upload rights confirmation must be true")
    return validate_project(project)


def validate_archive(
    project: object, media_ids: object, confirmation: object
) -> tuple[str, tuple[str, ...]]:
    if confirmation is not True:
        raise ConfigurationError(detail="Explicit reversible archive confirmation must be true")
    selected = validate_project(project)
    if (
        not isinstance(media_ids, (list, tuple))
        or not 1 <= len(cast("list[object] | tuple[object, ...]", media_ids)) <= 100
    ):
        raise ConfigurationError(detail="Archive requires 1 to 100 distinct media UUIDs")
    identifiers: list[str] = []
    for item in cast("list[object] | tuple[object, ...]", media_ids):
        if not isinstance(item, str):
            raise ConfigurationError(detail="Archive requires media UUIDs")
        try:
            identifiers.append(str(UUID(item)))
        except ValueError:
            raise ConfigurationError(detail="Archive requires media UUIDs") from None
    if len(set(identifiers)) != len(identifiers):
        raise ConfigurationError(detail="Archive requires distinct media UUIDs")
    return selected, tuple(identifiers)


def _native(client: FlowApiClient) -> None:
    if getattr(client.settings, "flow_host", "auto") == "labs.google":
        raise ConfigurationError(detail="Native media operations require the migrated Flow host")


def propagate_after_ack(
    error: BaseException,
    *,
    project: str,
    operation: Literal["upload", "archive", "delete"],
    known: tuple[str, ...],
    pending: tuple[str, ...] = (),
) -> None:
    """Raise safe uncertainty after acknowledgement; cancellation remains cancellation."""
    import asyncio

    from gflow_cli.errors import NativeMediaMutationUnknownError

    typed = NativeMediaMutationUnknownError(
        operation=operation,
        phase="cancelled" if isinstance(error, asyncio.CancelledError) else "response",
        project_id=project,
        known_media_ids=known,
        pending_media_ids=pending,
    )
    if isinstance(error, asyncio.CancelledError):
        vars(error)["gflow_native_media_unknown"] = typed
        raise error
    raise typed from error


async def upload_snapshot(client: FlowApiClient, project: str, path: Path) -> dict[str, Any]:
    from gflow_cli.api.transports.migrated_video_upload import (
        _upload_video_snapshot,  # pyright: ignore[reportPrivateUsage]
    )

    _native(client)
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    outcome: dict[str, Any] = {}
    try:
        try:
            media_id, _caption = await _upload_video_snapshot(
                page, project, path, rights_confirmed=True
            )
            outcome.update(
                media_id=media_id, project_id=project, scope="native-project-video-upload"
            )
        finally:
            import sys

            original = sys.exc_info()[1]
            try:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
            except BaseException:
                if original is None:
                    raise
                original.add_note("Native media browser checkin remains incomplete")

    except BaseException as error:
        if outcome.get("media_id"):
            propagate_after_ack(
                error, project=project, operation="upload", known=(outcome["media_id"],)
            )
        raise
    return outcome


async def archive(
    client: FlowApiClient, project: str, identifiers: tuple[str, ...]
) -> dict[str, Any]:
    from gflow_cli.api.transports.migrated_resources import trash_media

    _native(client)
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    acknowledged: list[str] = []
    try:
        try:
            acknowledged = await trash_media(page, project, list(identifiers))
        finally:
            import sys

            original = sys.exc_info()[1]
            try:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
            except BaseException:
                if original is None:
                    raise
                original.add_note("Native media browser checkin remains incomplete")

    except BaseException as error:
        if acknowledged:
            propagate_after_ack(
                error,
                project=project,
                operation="archive",
                known=tuple(acknowledged),
                pending=tuple(item for item in identifiers if item not in acknowledged),
            )
        raise
    return {
        "archived_media_ids": acknowledged,
        "project_id": project,
        "scope": "native-reversible-whole-batch-archive",
    }


@contextmanager
def upload_snapshot_context(
    path: Path, *, project: str, rights_confirmed: object, outcome: dict[str, Any]
) -> Generator[Path, None, None]:
    """Preserve acknowledged upload handles if private snapshot cleanup fails."""
    from gflow_cli.api.transports.native_video_snapshot import snapshot_video
    from gflow_cli.errors import NativeMediaMutationUnknownError

    selected = validate_upload(project, rights_confirmed)
    try:
        with snapshot_video(path, rights_confirmed=rights_confirmed) as private:
            yield private
    except ValueError:
        media_id = outcome.get("media_id")
        if isinstance(media_id, str):
            raise NativeMediaMutationUnknownError(
                operation="upload",
                phase="response",
                project_id=selected,
                known_media_ids=(media_id,),
            ) from None
        raise ConfigurationError(detail="Upload requires a stable bounded regular MP4") from None


async def delete(
    client: FlowApiClient, project_id: str, media_ids: object, confirm_delete: object = False
) -> dict[str, Any]:
    from gflow_cli.api.transports.native_media_delete import (
        delete_individual_media,
        validate_delete,
    )

    try:
        project, identifiers = validate_delete(project_id, media_ids, confirm_delete)
    except ValueError as error:
        raise ConfigurationError(detail=str(error)) from None
    _native(client)
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    outcome: dict[str, Any] = {}
    try:
        try:
            outcome = await delete_individual_media(page, project, identifiers, True)
        finally:
            import sys

            primary = sys.exc_info()[1]
            try:
                client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
            except BaseException:
                if primary is None:
                    raise
                primary.add_note("Permanent media browser checkin remains incomplete")
    except BaseException as error:
        if outcome:
            propagate_after_ack(error, project=project, operation="delete", known=identifiers)
        raise
    return outcome
