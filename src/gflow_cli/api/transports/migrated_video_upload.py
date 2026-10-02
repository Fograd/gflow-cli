"""Page-owned native MP4 ingestion, measured separately from image maseQ upload."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from gflow_cli.api.transports.migrated_composer import (
    TOOLBAR_ADD,
    UPLOAD_MENU_ITEM,
    MigratedComposer,
)


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
    """Upload through Flow's chooser; the account owner handles any rights dialog.

    Video ingestion is a resumable upload endpoint, not the image maseQ RPC. Never
    auto-accept the rights confirmation without an explicit per-request ownership assertion.
    """
    if not is_uuid(project_id):
        raise ValueError("Invalid project identifier")
    validate_video(path)
    await MigratedComposer().ensure_editor(page, project_id)
    caption = f"{path.stem}-{uuid4().hex[:8]}.mp4"
    reply: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def on_response(response: Any) -> None:
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
            if not reply.done():
                reply.set_result(media_id)
        except Exception as exc:
            if not reply.done():
                reply.set_exception(exc)

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
            if await dialogs.count() > dialogs_before:
                if not rights_confirmed:
                    raise UploadRightsRequiredError(
                        "Video rights confirmation required: affirm that you own upload rights "
                        "with X-Flow-Rights-Confirmed: true, or confirm in the logged-in browser"
                    )
                buttons = dialogs.last.get_by_role("button")
                # Measured video dialog order: cancel, agree persistently, agree once.
                # Never choose the middle button or change an account-wide preference.
                if await buttons.count() != 3:
                    raise ValueError("Video rights dialog changed; confirm in the browser")
                await buttons.nth(2).click(timeout=5000)
                dialogs_before = await dialogs.count()
            await asyncio.sleep(0.1)
        return await asyncio.wait_for(reply, timeout=max(0.1, deadline - time.monotonic())), caption
    finally:
        page.remove_listener("response", on_response)
