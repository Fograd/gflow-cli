"""Page-owned native MP4 ingestion, measured separately from image maseQ upload."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from gflow_cli.api.transports.migrated_composer import (
    TOOLBAR_ADD,
    UPLOAD_MENU_ITEM,
)
from gflow_cli.api.transports.native_video_snapshot import snapshot_video
from gflow_cli.errors import NativeMediaMutationUnknownError


class UploadRightsRequiredError(ValueError):
    """The account owner must affirm rights before video bytes are ingested."""


MAX_VIDEO_BYTES = 250 * 1024 * 1024  # Local memory budget, not a claimed Google limit.


def is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def validate_video(path: Path) -> None:
    """Accept local ISO-BMFF MP4 only; reject oversized reads before browser allocation."""
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise ValueError("Upload requires an existing local .mp4 file")
    size = path.stat().st_size
    if not 12 <= size <= MAX_VIDEO_BYTES:
        raise ValueError("MP4 must contain 12 bytes to 250 MiB")
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] != b"ftyp":
        raise ValueError("MP4 must start with an ISO-BMFF ftyp box")


def parse_upload_reply(text: str, project_id: str) -> str:
    """Reject unrelated, malformed, or cross-project upload responses."""
    parsed: Any = json.loads(text)
    data = cast("dict[str, Any]", parsed)
    if not isinstance(parsed, dict) or not isinstance(data.get("media"), dict):
        raise ValueError("Native upload returned no media record")
    media = cast("dict[str, Any]", data["media"])
    media_id = data.get("mediaId")
    if not is_uuid(media_id) or media.get("name") != media_id:
        raise ValueError("Native upload returned an invalid media identifier")
    if media.get("projectId") != project_id:
        raise ValueError("Native upload returned another project")
    return str(media_id)


async def upload_video(
    page: Any, project_id: str, path: Path, *, rights_confirmed: bool = False
) -> tuple[str, str]:
    """Prepare a private stable snapshot before any page action."""
    if rights_confirmed is not True:
        raise UploadRightsRequiredError("Explicit per-request upload rights must be true")
    if not is_uuid(project_id):
        raise ValueError("Invalid project identifier")
    uploaded: tuple[str, str] | None = None
    try:
        with snapshot_video(path, rights_confirmed=rights_confirmed) as private:
            uploaded = await _upload_video_snapshot(
                page, project_id, private, rights_confirmed=True
            )
        return uploaded
    except Exception:
        if uploaded is not None:
            raise NativeMediaMutationUnknownError(
                operation="upload",
                phase="response",
                project_id=project_id,
                known_media_ids=(uploaded[0],),
            ) from None
        raise


async def _upload_video_snapshot(
    page: Any, project_id: str, path: Path, *, rights_confirmed: bool = False
) -> tuple[str, str]:
    """Upload through Flow's chooser; the account owner handles any rights dialog.

    Video ingestion is a resumable upload endpoint, not the image maseQ RPC. Never
    auto-accept the rights confirmation without an explicit per-request ownership assertion.
    """
    if rights_confirmed is not True:
        raise UploadRightsRequiredError("Explicit per-request upload rights must be true")
    if not is_uuid(project_id):
        raise ValueError("Invalid project identifier")
    validate_video(path)
    # Resources imports our UUID validator; defer this import to avoid a cycle.
    from gflow_cli.api.transports.migrated_resources import read_project_payload

    # Upload uses the project toolbar, including cohorts without generation settings.
    await read_project_payload(page, project_id)
    caption = f"{path.stem}-{uuid4().hex[:8]}.mp4"
    reply: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    dispatched = False
    known_media: str | None = None

    def on_request(request: Any) -> None:
        nonlocal dispatched
        url = urlsplit(str(request.url))
        if (
            url.hostname == "flow.google.com"
            and url.path == f"/upload/v1/flow/upload/video/{project_id}"
            and request.method == "POST"
        ):
            dispatched = True

    async def on_response(response: Any) -> None:
        nonlocal known_media
        url = urlsplit(str(response.url))
        if (
            url.hostname != "flow.google.com"
            or url.path != f"/upload/v1/flow/upload/video/{project_id}"
            or response.request.method != "POST"
            or reply.done()
        ):
            return
        try:
            text = await response.text()
            # Resumable initiation returns an empty response; the final POST carries JSON.
            if not text:
                return
            if response.status != 200:
                raise ValueError(f"Native video upload failed with HTTP {response.status}")
            media_id = parse_upload_reply(text, project_id)
            known_media = media_id
            if not reply.done():
                reply.set_result(media_id)
        except Exception as exc:
            if not reply.done():
                reply.set_exception(exc)

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        await page.locator(TOOLBAR_ADD).first.click(timeout=5000)
        async with page.expect_file_chooser(timeout=10000) as chooser_info:
            await page.locator(UPLOAD_MENU_ITEM).first.click(timeout=5000)
        chooser = await chooser_info.value
        content = await asyncio.to_thread(path.read_bytes)
        if len(content) > MAX_VIDEO_BYTES:
            raise ValueError("MP4 grew beyond the upload memory budget")
        dialogs_before = await page.locator("mat-dialog-container").count()
        await chooser.set_files({"name": caption, "mimeType": "video/mp4", "buffer": content})
        deadline = time.monotonic() + 120
        while not reply.done() and time.monotonic() < deadline:
            dialogs = page.locator("mat-dialog-container")
            dialog_count = await dialogs.count()
            if dialog_count > dialogs_before:
                if not rights_confirmed:
                    raise UploadRightsRequiredError(
                        "Video rights confirmation required: affirm that you own upload rights "
                        "with X-Flow-Rights-Confirmed: true, or confirm in the logged-in browser"
                    )
                # Patchright queryCount misreads negative nth selectors as empty.
                buttons = dialogs.nth(dialog_count - 1).get_by_role("button")
                # Measured video dialog order: cancel, agree persistently, agree once.
                # Never choose the middle button or change an account-wide preference.
                # Angular mounts the dialog shell before its buttons are ready.
                await buttons.nth(2).wait_for(state="visible", timeout=5000)
                mount_deadline = min(deadline, time.monotonic() + 5)
                while await buttons.count() != 3:
                    if time.monotonic() >= mount_deadline:
                        raise ValueError("Video rights dialog changed; confirm in the browser")
                    await asyncio.sleep(0.1)
                await buttons.nth(2).click(timeout=5000)
                dialogs_before = await dialogs.count()
            await asyncio.sleep(0.1)
        return await asyncio.wait_for(reply, timeout=max(0.1, deadline - time.monotonic())), caption
    except asyncio.CancelledError as exc:
        if dispatched:
            vars(exc)["gflow_native_media_unknown"] = NativeMediaMutationUnknownError(
                operation="upload",
                phase="cancelled",
                project_id=project_id,
                known_media_ids=(known_media,) if known_media else (),
            )
        raise
    except Exception:
        if dispatched:
            raise NativeMediaMutationUnknownError(
                operation="upload",
                phase="response",
                project_id=project_id,
                known_media_ids=(known_media,) if known_media else (),
            ) from None
        raise
    finally:
        original = sys.exc_info()[1]
        cleanup_error: BaseException | None = None
        for event, callback in (("request", on_request), ("response", on_response)):
            try:
                page.remove_listener(event, callback)
            except BaseException as error:
                cleanup_error = cleanup_error or error
        if reply.done() and not reply.cancelled():
            reply.exception()
        if cleanup_error is not None:
            if original is not None:
                original.add_note("Native upload listener cleanup remains incomplete")
            elif isinstance(cleanup_error, asyncio.CancelledError):
                if dispatched:
                    vars(cleanup_error)["gflow_native_media_unknown"] = (
                        NativeMediaMutationUnknownError(
                            operation="upload",
                            phase="cancelled",
                            project_id=project_id,
                            known_media_ids=(known_media,) if known_media else (),
                        )
                    )
                raise cleanup_error
            elif dispatched or known_media:
                raise NativeMediaMutationUnknownError(
                    operation="upload",
                    phase="response",
                    project_id=project_id,
                    known_media_ids=(known_media,) if known_media else (),
                ) from None
            else:
                raise ValueError("Native upload listener cleanup incomplete") from None
