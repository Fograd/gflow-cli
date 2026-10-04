"""Response-scoped cleanup includes Range refusal, send failure and cancellation."""

from __future__ import annotations

import shutil
from pathlib import Path

from starlette.responses import FileResponse
from starlette.types import Receive, Scope, Send


class EphemeralFileResponse(FileResponse):
    def __init__(self, path: Path, directory: Path, *, media_type: str = "video/mp4") -> None:
        super().__init__(
            path, media_type=media_type, filename=path.name, headers={"Cache-Control": "no-store"}
        )
        self.directory = directory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # This unique server-owned directory contains only this read response.
            # Unlinking in finally also runs on early Range responses and cancellation.
            shutil.rmtree(self.directory, ignore_errors=True)
