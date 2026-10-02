"""Bounded private recovery handles for already generated images; never regenerate."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from gflow_cli.errors import MediaDownloadError, ProblemDetails
from gflow_cli.winsec import ensure_profile_hardened

MAX_JOURNAL = 65536
MAX_IMAGES = 4
MAX_RECOVERY_FILE = 250 * 1024 * 1024


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Invalid image recovery handle")
    return value


def _invocation(value: str) -> str:
    return str(uuid.UUID(value))


def _image_record(image: Any) -> dict[str, Any]:
    record: dict[str, Any] = {"media_name": _identifier(image.media_name)}
    workflow = getattr(image, "workflow_id", None)
    if workflow:
        record["workflow_id"] = _identifier(workflow)
    seed = getattr(image, "seed", None)
    if isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed <= 2147483647:
        record["seed"] = seed
    dimensions = getattr(image, "dimensions", None)
    if isinstance(dimensions, (tuple, list)) and len(cast(list[Any], dimensions)) == 2:
        sizes = cast(tuple[Any, Any], dimensions)
        if all(
            isinstance(size, int) and not isinstance(size, bool) and 0 < size <= 32768
            for size in sizes
        ):
            record["dimensions"] = {"width": sizes[0], "height": sizes[1]}
    return record


class ImageJournal:
    def __init__(self, root: Path, images: list[Any], *, invocation: str | None = None):
        if not 1 <= len(images) <= MAX_IMAGES:
            raise ValueError("Image recovery supports one to four outputs")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.invocation = _invocation(
            invocation or os.environ.get("GFLOW_IMAGE_RECOVERY_ID") or str(uuid.uuid4())
        )
        journal_directory = self.root / ".gflow-image-recovery"
        if journal_directory.is_symlink():
            raise ValueError("Image recovery directory cannot be a symlink")
        journal_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal_directory.chmod(0o700)
        ensure_profile_hardened(journal_directory)
        self.path = journal_directory / f"{self.invocation}.json"
        self.data: dict[str, Any] = {
            "version": 1,
            "invocation": self.invocation,
            "images": [_image_record(image) for image in images],
        }
        self._write()

    def _write(self) -> None:
        if self.path.is_symlink():
            raise ValueError("Image recovery journal cannot be a symlink")
        raw = json.dumps(self.data, separators=(",", ":")).encode()
        if len(raw) > MAX_JOURNAL:
            raise ValueError("Image recovery journal is too large")
        fd, temporary = tempfile.mkstemp(prefix=".image-recovery-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                fchmod = getattr(os, "fchmod", None)
                if fchmod is not None:
                    fchmod(stream.fileno(), 0o600)
                else:
                    Path(temporary).chmod(0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if hasattr(os, "O_DIRECTORY"):
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def complete(self, index: int, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root) or path.is_symlink():
            raise ValueError("Image recovery output is outside its directory")
        if not resolved.is_file() or not 0 < resolved.stat().st_size <= MAX_RECOVERY_FILE:
            raise ValueError("Image recovery output is missing, empty or too large")
        self.data["images"][index]["relative_path"] = str(resolved.relative_to(self.root))
        self._write()


def read_journal(root: Path, invocation: str) -> dict[str, Any]:
    """Read only the expected invocation, stripping missing or unsafe local paths."""
    try:
        root = root.resolve()
        invocation = _invocation(invocation)
        directory = root / ".gflow-image-recovery"
        path = directory / f"{invocation}.json"
        if directory.is_symlink() or path.is_symlink():
            return {}
        initial = path.lstat()
        if not stat.S_ISREG(initial.st_mode):
            return {}
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            final = path.lstat()
            identity = (info.st_dev, info.st_ino)
            if (
                identity != (initial.st_dev, initial.st_ino)
                or identity != (final.st_dev, final.st_ino)
                or stat.S_ISLNK(final.st_mode)
            ):
                return {}
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JOURNAL:
                return {}
            raw = stream.read(MAX_JOURNAL + 1)
        data = json.loads(raw)
        if data.get("version") != 1 or data.get("invocation") != invocation:
            return {}
        items = data["images"]
        if not isinstance(items, list) or not 1 <= len(cast(list[Any], items)) <= MAX_IMAGES:
            return {}
        clean: list[dict[str, Any]] = []
        for item in cast(list[dict[str, Any]], items):
            try:
                entry: dict[str, Any] = {"media_name": _identifier(item["media_name"])}
                if item.get("workflow_id"):
                    entry["workflow_id"] = _identifier(item["workflow_id"])
            except (ValueError, KeyError, TypeError):
                continue
            seed = item.get("seed")
            if isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed <= 2147483647:
                entry["seed"] = seed
            dimensions: Any = item.get("dimensions", {})
            if isinstance(dimensions, dict):
                sized = cast(dict[str, Any], dimensions)
                if all(
                    isinstance(sized.get(k), int)
                    and not isinstance(sized[k], bool)
                    and 0 < sized[k] <= 32768
                    for k in ("width", "height")
                ):
                    entry["dimensions"] = {key: sized[key] for key in ("width", "height")}
            relative = item.get("relative_path")
            if (
                isinstance(relative, str)
                and len(relative) <= 1024
                and not Path(relative).is_absolute()
            ):
                candidate = root / relative
                resolved = candidate.resolve()
                if (
                    resolved.is_relative_to(root)
                    and not candidate.is_symlink()
                    and candidate.is_file()
                    and 0 < candidate.stat().st_size <= MAX_RECOVERY_FILE
                ):
                    entry["local_path"] = str(resolved)
            clean.append(entry)
        return {"images": clean}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


class ImagePartialDownloadError(MediaDownloadError):
    def __init__(
        self, journal: ImageJournal | None = None, *, recovery: dict[str, Any] | None = None
    ):
        super().__init__(
            detail=(
                "Images were generated, but not every output could be downloaded. "
                "Inspect preserved handles before generating again."
            ),
            retryable=False,
        )
        self.recovery = recovery or (
            read_journal(journal.root, journal.invocation) if journal else {"images": []}
        )

    def to_problem_details(self) -> ProblemDetails:
        result = super().to_problem_details()
        cast(dict[str, Any], result)["imageRecovery"] = self.recovery
        return result


def create_journal(root: Path, images: list[Any]) -> ImageJournal:
    """A persistence failure still reports safe handles in the immediate error."""
    handles = {"images": [_image_record(image) for image in images]}
    try:
        return ImageJournal(root, images)
    except Exception:
        raise ImagePartialDownloadError(recovery=handles) from None


async def download_images(
    client: Any,
    images: list[Any],
    targets: list[Path],
    *,
    on_checkpoint: Callable[[ImageJournal], None] | None = None,
) -> list[Path]:
    if len(images) != len(targets) or not targets:
        raise ValueError("Image targets must match generated outputs")
    root = Path(os.path.commonpath([str(path.absolute().parent) for path in targets]))
    memory: dict[str, Any] = {"images": [_image_record(image) for image in images]}
    saved: list[Path] = []
    try:
        journal = create_journal(root, images)
        if on_checkpoint is not None:
            on_checkpoint(journal)
        for index, (image, target) in enumerate(zip(images, targets, strict=True)):
            path = await client.download_image(image, target)
            resolved = path.resolve()
            if (
                not resolved.is_relative_to(journal.root)
                or path.is_symlink()
                or not resolved.is_file()
                or not 0 < resolved.stat().st_size <= MAX_RECOVERY_FILE
            ):
                raise ValueError("Image output is missing, unsafe or too large")
            memory["images"][index]["local_path"] = str(resolved)
            journal.complete(index, path)
            if on_checkpoint is not None:
                on_checkpoint(journal)
            saved.append(path)
    except Exception:
        raise ImagePartialDownloadError(recovery=memory) from None
    return saved
