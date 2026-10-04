# SPDX-License-Identifier: MIT
"""MCP tool definitions — maps MCP tools to gflow-cli core functions.

Each tool is registered on the shared MCPServer instance and delegates
to FlowWorker / DataStore / data.queries for actual execution.

Rate limiting: a token-bucket (capacity=8, refill=1/20s) prevents runaway
agentic loops from burning credits. There is NO credit-budget accounting —
rate limiting is the only spend brake (#495).

Task claiming: the direct-execution path enqueues a task then claims it via
the atomic ``QueueRepository.claim_task`` (the same BEGIN IMMEDIATE claim the
daemon poll loop uses), so the two paths can never execute the same row. The
former per-profile asyncio lock is gone — serialising concurrent same-profile
BROWSER sessions is the browser lease's job (production-readiness plan slice
D); until it lands, two distinct same-profile tasks may drive two browsers
concurrently (the claim still prevents double-executing one task).
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
import uuid
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast

import structlog
from pydantic import StrictBool, StrictInt

from gflow_cli import auth as auth_mod
from gflow_cli._cli_helpers import _FLOW_ID_RE
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.image import AgentInstruction, GenerateImageRequest, ImageRef
from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.api.native_captcha import native_captcha_or_none
from gflow_cli.api.native_catalogs import (
    validate_project_catalog_resume,
    validate_project_catalogs,
    validate_project_traversal,
)
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.api.video import VIDEO_DURATION_CHOICES, is_media_uuid
from gflow_cli.auth import verification
from gflow_cli.cli_image import lookup_project_in_catalog
from gflow_cli.cli_instructions import classify_refs
from gflow_cli.config import UiMode, get_settings
from gflow_cli.data.models import AssetKind, AssetLookup
from gflow_cli.data.queries import list_projects
from gflow_cli.data.repository import DataRepository, verified_local_path
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError, GFlowError, is_retryable
from gflow_cli.mcp.server import server
from gflow_cli.profile_store import (
    NoDefaultProfileError,
    NoProfilesError,
    resolve_profile,
)
from gflow_cli.project_output import local_project_payload
from gflow_cli.services.credits import inspect_all_profiles as inspect_all_credit_profiles
from gflow_cli.services.credits import inspect_profile as inspect_credit_profile
from gflow_cli.services.image_aspect import aspect_decision_metadata, resolve_image_aspect
from gflow_cli.services.media_recovery import download_media
from gflow_cli.services.native_characters import (
    create_character_from_images as native_create_character_from_images,
)
from gflow_cli.services.native_characters import (
    normalize_preset_voice,
    validate_character_selector,
    validate_create_inputs,
    validate_update_inputs,
)
from gflow_cli.services.native_characters import (
    update_character as native_update_character,
)
from gflow_cli.worker import codec
from gflow_cli.worker.daemon import FlowWorker
from gflow_cli.worker.queue import QueueRepository

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Token bucket rate limiter
# ---------------------------------------------------------------------------

_BUCKET_CAPACITY = 8
_BUCKET_REFILL_RATE = 1 / 20  # 1 token every 20 seconds


class _TokenBucket:
    """Simple token-bucket rate limiter for generation tools."""

    def __init__(self, capacity: int = _BUCKET_CAPACITY, refill_rate: float = _BUCKET_REFILL_RATE):
        self._capacity = capacity
        self._tokens = float(capacity)
        self._refill_rate = refill_rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire a token. Returns True if acquired, False if rate-limited."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False


_rate_limiter = _TokenBucket()


_profile_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


def _profile_lock(profile: str) -> asyncio.Lock:
    """Serialize this server's browser work on one profile (#862).

    Tool calls run in the server's own process, and a second same-process lease on a
    profile fails fast by design (waiting on yourself would deadlock), so two calls
    arriving together — a client retry, two agents on one server — must queue here.
    Different profiles still run concurrently. Held per loop — weakly, so a finished
    loop takes its locks with it — because an `asyncio.Lock` belongs to the loop that
    first contends it, and a loop id can be reused once that loop is gone.
    """
    locks = _profile_locks.setdefault(asyncio.get_running_loop(), {})
    return locks.setdefault(profile, asyncio.Lock())


def _rate_limited_envelope() -> dict[str, Any]:
    """The ONE rate-limited refusal shape (#498) — RFC 9457 problem details.

    Both generate tools refuse with this exact envelope; the refusal happens
    before the ``@_guarded`` funnel, which is why #473's unification missed it.
    Built from the canonical ``RateLimitError`` via ``_gflow_error_dict`` so
    the type URI, ``message``, and ``retryable`` stay identical to every other
    surface (post-merge review of the #495-#501 wave: a hand-rolled literal
    here minted a second '…/rate-limited' spelling and dropped ``retryable``
    from the canonical retryable case).
    """
    from gflow_cli.errors import RateLimitError

    err = RateLimitError(
        "Generation rate limit reached (token bucket: capacity 8, "
        "refill 1 per 20 s). Please wait before making another request."
    )
    return {"status": "rate_limited", "error": _gflow_error_dict(err)}


# Sentinel meaning "auto-resolve the profile like the CLI" (see
# _resolve_and_validate_profile). Shared constant, not a repeated literal (S1192).
_DEFAULT_PROFILE = "default"


def _adapt_tools(tools: list[dict[str, Any]] | None) -> tuple[str, ...] | dict[str, Any]:
    """Validate + adapt the MCP ``tools`` array to CLI ``--tool`` specs.

    Returns the spec tuple on success, or a structured error dict (to return to
    the agent) when an item is malformed — so a bad ``tools`` payload fails
    cleanly rather than as an uncaught error once generation is wired.
    """
    from pydantic import ValidationError

    from gflow_cli.tools.invocation import tool_specs_from_invocations

    try:
        return tool_specs_from_invocations(tools)
    except ValidationError as exc:
        log.warning("mcp.tool.invalid_tools", error=str(exc))
        return {
            "status": "invalid_tools",
            "error": (
                "Each item in 'tools' must be {'name': <slug>, 'options': {k: v}}. "
                f"Validation failed: {exc}"
            ),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_UNKNOWN_ERROR_TYPE = "https://gflow-cli.dev/errors/unknown"


def _masked_unexpected_dict(exc: Exception) -> dict[str, Any]:
    """RFC-9457 envelope for a non-GFlowError (issue #473).

    The exception CLASS name is safe to share; the message is NOT — it can
    embed filesystem paths, profile names, or token text — so it goes to the
    server-side log only, never to the MCP client."""
    detail = f"Unexpected {type(exc).__name__}; details were logged server-side."
    return {
        "type": _UNKNOWN_ERROR_TYPE,
        "title": "Unexpected Error",
        "status": 500,
        "detail": detail,
        # Same key set as _gflow_error_dict so clients see ONE envelope schema.
        "message": detail,
        "retryable": False,
    }


def _guarded(
    fn: Callable[..., Awaitable[dict[str, Any]]],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Single error funnel every MCP tool routes through (issue #473).

    GFlowError -> structured problem-details envelope; anything else -> the
    masked generic envelope + a full server-side log. Tool-specific except
    blocks may still run first for richer envelopes (task ids, partial
    results); this is the outermost backstop, so raw exception text can
    never reach the client via the framework's default str(exc) path."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await fn(*args, **kwargs)
        except GFlowError as exc:
            log.error("mcp.tool.gflow_error", tool=fn.__name__, error=str(exc))
            return _error_payload(_gflow_error_dict(exc))
        except Exception as exc:  # noqa: BLE001 — the funnel IS the handler
            log.exception("mcp.tool.unexpected_error", tool=fn.__name__, exc_info=exc)
            return _error_payload(_masked_unexpected_dict(exc))

    wrapper.__gflow_guarded__ = True  # type: ignore[attr-defined]
    return wrapper


def _resolve_and_validate_profile(profile: str) -> str | dict[str, Any]:
    """Resolve the requested profile name using the same precedence as the CLI.

    When *profile* is ``"default"`` (the MCP sentinel meaning "auto-pick"),
    this runs the full CLI resolution chain:

    1. ``GFLOW_CLI_PROFILE`` env var
    2. ``config.toml`` ``default_profile``
    3. Auto-select the only profile that exists on disk

    When *profile* is any other value (an explicit name the agent passed in),
    it is forwarded to ``resolve_profile()`` as-is so the same validation runs.

    Returns the resolved profile name string on success, or a ready-to-return
    error dict on failure.
    """
    try:
        # Pass None when the agent omitted the profile (left it as "default")
        # so resolve_profile runs the full auto-detection chain.
        cli_flag: str | None = None if profile == "default" else profile
        resolved = resolve_profile(cli_flag)
    except NoProfilesError:
        return {
            "status": "error",
            "error": {
                "type": "https://gflow-cli.dev/errors/no-profile",
                "title": "No Profile Found",
                "status": 400,
                "detail": (
                    "No gflow profiles exist. Run `gflow auth login --browser chrome` first."
                ),
            },
        }
    except NoDefaultProfileError as exc:
        return {
            "status": "error",
            "error": {
                "type": "https://gflow-cli.dev/errors/no-default-profile",
                "title": "No Default Profile",
                "status": 400,
                "detail": (
                    f"Multiple profiles exist ({', '.join(exc.available)}) but none is set as "
                    "default. Pass profile=<name> explicitly, or run "
                    "`gflow auth use <name>` / set GFLOW_CLI_PROFILE."
                ),
                "available_profiles": exc.available,
            },
        }

    # Sanity-check: the profile directory must exist on disk. If auth was never
    # completed the FlowApiClient would fail with a cryptic Playwright error;
    # surface a clear message here instead.
    settings = get_settings()
    profile_dir = settings.profile_subdir(resolved)
    if not profile_dir.exists():
        return {
            "status": "error",
            "error": {
                "type": "https://gflow-cli.dev/errors/no-profile",
                "title": "Profile Directory Not Found",
                "status": 400,
                "detail": (
                    f"Profile {resolved!r} resolved but its directory does not exist: "
                    f"{profile_dir}. Run `gflow auth login --browser chrome` first."
                ),
            },
        }

    log.debug("mcp.tool.profile_resolved", requested=profile, resolved=resolved)
    return resolved


def _enqueue_generation_task(
    *,
    profile: str,
    task_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue a generation task into generation_queue and return task handle immediately."""
    settings = get_settings()
    db_path = settings.resolved_db_path()
    task_id = str(uuid.uuid4())

    with DataStore.open(db_path) as store:
        data_repo = DataRepository(store)
        profile_dir = settings.profile_subdir(profile)
        data_repo.upsert_profile(profile, profile_dir)

        ref_err = _resolve_payload_refs(data_repo, profile, payload, task_type)
        if ref_err is not None:
            return ref_err

        versioned_payload = dict(payload)
        versioned_payload.setdefault("schema_version", codec.CURRENT_SCHEMA_VERSION)

        QueueRepository(store).enqueue_task(
            task_id=task_id,
            profile_name=profile,
            task_type=task_type,
            payload=versioned_payload,
        )

    log.info("mcp.tool.task_enqueued", task_id=task_id, task_type=task_type)
    return {
        "status": "pending",
        "task_id": task_id,
        "task_type": task_type,
    }


async def _run_generation_task(
    *,
    profile: str,
    task_type: str,
    payload: dict[str, Any],
    wait: bool = True,
) -> dict[str, Any]:
    """Enqueue a generation task and either return handle immediately or wait for completion."""
    if not wait:
        return _enqueue_generation_task(
            profile=profile,
            task_type=task_type,
            payload=payload,
        )

    settings = get_settings()
    db_path = settings.resolved_db_path()

    task_id = str(uuid.uuid4())

    try:
        # 1. Enqueue the task (short-lived connection, closed before the worker
        #    opens its own — WAL allows a single writer at a time).
        with DataStore.open(db_path) as store:
            data_repo = DataRepository(store)

            # Ensure the profile FK exists before inserting the queue row.
            profile_dir = settings.profile_subdir(profile)
            data_repo.upsert_profile(profile, profile_dir)

            # Resolve remote-ref UUIDs to local file paths (video paths only) so
            # the attach reuses the proven local-upload path; an unresolvable
            # UUID fails fast here instead of timing out in the browser (#237).
            ref_err = _resolve_payload_refs(data_repo, profile, payload, task_type)
            if ref_err is not None:
                return ref_err

            # Task C2: stamp the current queue schema version onto every
            # freshly built payload at the enqueue site (additive, top-level —
            # setdefault so it never overwrites a version already present).
            # Encoding is centralized here; decoding is centralized at
            # claim/execution.
            versioned_payload = dict(payload)
            versioned_payload.setdefault("schema_version", codec.CURRENT_SCHEMA_VERSION)

            QueueRepository(store).enqueue_task(
                task_id=task_id,
                profile_name=profile,
                task_type=task_type,
                payload=versioned_payload,
            )

        log.info(
            "mcp.tool.task_enqueued",
            task_id=task_id,
            task_type=task_type,
            profile=profile,
        )

        # 2. Atomically claim the task we just enqueued, then run it. The claim
        #    (shared with the daemon poll loop) is what guarantees this row is
        #    executed at most once. A None claim = invalid payload failed at
        #    claim time (no browser) or already taken; the read-back reports it.
        async with _profile_lock(profile):
            worker = FlowWorker(profile_name=profile, db_path=str(db_path))
            try:
                claimed = worker.repo.claim_task(task_id, claimant=f"mcp:{profile}")
                if claimed is not None:
                    await worker.process_task(claimed)
            finally:
                worker.close()

        # 3. Read the final task state back.
        with DataStore.open(db_path) as store:
            completed_task = QueueRepository(store).get_task(task_id)
            if completed_task is None:
                return {
                    "status": "error",
                    "error": f"Task {task_id!r} disappeared from queue after execution.",
                }

            # Treat anything other than an explicit "completed" as a failure —
            # a row stuck in "processing"/"pending" must not be reported as a
            # success with an empty file list.
            if completed_task.status != "completed":
                log.warning(
                    "mcp.tool.task_failed",
                    task_id=task_id,
                    status=completed_task.status,
                    error=completed_task.error,
                )
                failed: dict[str, Any] = {
                    "status": "failed",
                    "task_id": task_id,
                    "error": completed_task.error
                    or {"detail": f"Task ended in unexpected status {completed_task.status!r}"},
                }
                checkpoint = completed_task.checkpoint or {}
                ids = checkpoint.get("media_ids")
                workflows = checkpoint.get("workflow_ids")
                if (
                    task_type in ("t2v", "i2v", "r2v")
                    and payload.get("count", 1) > 1
                    and checkpoint.get("phase") == "completed"
                    and isinstance(ids, list)
                    and isinstance(workflows, list)
                    and len(cast(list[Any], ids)) == payload["count"]
                    and len(cast(list[Any], workflows)) == payload["count"]
                ):
                    from uuid import UUID

                    native_ids = [str(UUID(value)) for value in cast(list[Any], ids)]
                    native_workflows = [str(UUID(value)) for value in cast(list[Any], workflows)]
                    native_project = str(UUID(checkpoint["project_id"]))
                    if (
                        len(set(native_ids + native_workflows)) != payload["count"] * 2
                        or native_project in native_ids + native_workflows
                    ):
                        raise ValueError("Partial batch checkpoint identities are invalid")
                    files: list[str] = []
                    for identifier in native_ids:
                        record = DataRepository(store).get_asset_by_flow_media_id(
                            profile, identifier
                        )
                        if record is not None and record.flow_project_id == native_project:
                            files.extend(
                                str(file.path)
                                for file in record.local_files
                                if file.path is not None
                            )
                    failed.update(
                        flow_project_id=native_project,
                        flow_media_ids=native_ids,
                        flow_workflow_ids=native_workflows,
                        files=files,
                    )
                return failed

            # Resolve local file paths from the asset catalog.
            file_paths: list[str] = []
            flow_project_id: str | None = None
            flow_workflow_id: str | None = None
            batch_ids: list[str] = []
            batch_workflows: list[str] = []
            checkpoint = completed_task.checkpoint or {}
            candidates = checkpoint.get("media_ids")
            if (
                task_type in ("t2v", "i2v", "r2v")
                and completed_task.payload.get("count", 1) > 1
                and checkpoint.get("phase") == "completed"
                and isinstance(candidates, list)
                and len(cast(list[Any], candidates)) == completed_task.payload["count"]
            ):
                from uuid import UUID

                batch_ids = [str(UUID(value)) for value in cast(list[Any], candidates)]
                if len(set(batch_ids)) != len(batch_ids):
                    raise ValueError("Batch task checkpoint has duplicate outputs")
                for identifier in batch_ids:
                    record = DataRepository(store).get_asset_by_flow_media_id(profile, identifier)
                    if record is None:
                        raise ValueError("Batch output asset is unavailable")
                    if flow_project_id is None:
                        flow_project_id = record.flow_project_id
                    if record.flow_project_id != flow_project_id:
                        raise ValueError("Batch outputs have different project scopes")
                    if record.flow_workflow_id is not None:
                        batch_workflows.append(record.flow_workflow_id)
                    file_paths.extend(
                        str(file.path) for file in record.local_files if file.path is not None
                    )
                flow_workflow_id = batch_workflows[0] if batch_workflows else None
            elif completed_task.flow_media_id:
                asset = DataRepository(store).get_asset_by_flow_media_id(
                    profile,
                    completed_task.flow_media_id,
                )
                if asset:
                    flow_project_id = asset.flow_project_id
                    flow_workflow_id = asset.flow_workflow_id
                    if asset.local_files:
                        file_paths = [
                            str(lf.path) for lf in asset.local_files if lf.path is not None
                        ]

        log.info(
            "mcp.tool.task_completed",
            task_id=task_id,
            flow_project_id=flow_project_id,
            flow_media_id=completed_task.flow_media_id,
            file_count=len(file_paths),
        )

        aspect_metadata: dict[str, str] = {}
        checkpoint_result = (completed_task.checkpoint or {}).get("result")
        if isinstance(checkpoint_result, dict):
            expected = {
                "requestedAspectRatio": "auto",
                "resolvedAspectRatio": completed_task.payload.get("aspect"),
                "aspectPolicy": "derived-first-reference-nearest-supported-v1",
            }
            if checkpoint_result == expected and expected["resolvedAspectRatio"] in {
                "16:9",
                "9:16",
                "1:1",
                "4:3",
                "3:4",
            }:
                aspect_metadata = cast("dict[str, str]", expected)

        return {
            "status": "completed",
            **aspect_metadata,
            "task_id": task_id,
            "flow_project_id": flow_project_id,
            "flow_media_id": completed_task.flow_media_id,
            "flow_workflow_id": flow_workflow_id,
            "files": file_paths,
            **(
                {"flow_media_ids": batch_ids, "flow_workflow_ids": batch_workflows}
                if batch_ids
                else {}
            ),
        }

    except GFlowError as exc:
        log.error("mcp.tool.gflow_error", task_id=task_id, error=str(exc))
        return {
            "status": "error",
            "task_id": task_id,
            "error": _gflow_error_dict(exc),
        }
    except Exception as exc:
        log.exception("mcp.tool.unexpected_error", task_id=task_id, exc_info=exc)
        return {
            "status": "error",
            "task_id": task_id,
            "error": _masked_unexpected_dict(exc),
        }


_BAD_PARAM_TYPE = "https://gflow-cli.dev/errors/bad-parameter"

# UUID (Flow media id) vs on-disk path discriminator for image references.


def _bad_param(title: str, detail: str) -> dict[str, Any]:
    """Build the standard RFC 9457 bad-parameter (400) error envelope."""
    return {
        "status": "error",
        "error": {"type": _BAD_PARAM_TYPE, "title": title, "status": 400, "detail": detail},
    }


def _resolve_ref_local_path(
    data_repo: DataRepository,
    profile: str,
    ref_id: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve a remote media-id reference to a local image file path.

    v0.25.0 (#237 fix): generated media do not appear in Flow's frame/reference
    picker search — Flow does not index generation prompts and generated assets
    carry no display name — so a UUID ref cannot be attached by a picker name
    search (that was the release-blocking bug). Instead it is attached by
    re-using its already-on-disk file through the proven local-upload path.

    Returns ``(local_path, None)`` or ``(None, error_envelope)``. Fail-fast
    cases: a UUID absent from the catalog → *Reference Not Found*; a catalogued
    asset with no local file on disk → *Reference Not On Disk*. (Automatic
    download-by-media-id for the on-disk-missing case is a planned follow-up;
    for now the caller re-generates or passes a local path.)
    """
    asset = data_repo.get_asset_by_any_id(profile, ref_id)
    if asset is None:
        return None, _bad_param(
            "Reference Not Found",
            f"'{ref_id}' was not found in your asset catalog for profile "
            f"{profile!r}. Generate the image first, or pass a local file path.",
        )
    for local_file in asset.local_files:
        if (path := verified_local_path(local_file)) is not None:
            return str(path), None
    return None, _bad_param(
        "Reference Not On Disk",
        f"'{ref_id}' is in your catalog but has no local image file on disk to "
        "attach. Re-generate it, or pass a local file path for the frame.",
    )


# Video task types whose media-id refs are resolved to local file paths and
# attached via the local-upload path (#237 fix — see _resolve_ref_local_path):
# the video FRAME picker does not surface generated media, so there is no
# existing tile to select. Image task types DO surface generated media in the
# reference picker, so their refs are enriched (not rewritten) and attached by
# selecting the existing asset — see _enrich_image_refs.
_VIDEO_TASK_TYPES = frozenset({"t2v", "i2v", "r2v"})


def _enrich_image_refs(
    data_repo: DataRepository,
    profile: str,
    payload: dict[str, Any],
) -> None:
    """Annotate each media-id ref in an image ``payload`` with its Flow
    ``display_name`` and on-disk ``local_path`` (best-effort), so the transport
    can attach it by **selecting the already-existing Flow asset** in the
    reference picker — the preferred path (no duplicate upload) — with the local
    file as an upload fallback. Never errors: an uncatalogued UUID is still a
    valid media id to attach in place (PR #245 — image refs pass through).
    """
    refs = payload.get("refs")
    if not refs:
        return
    meta: dict[str, dict[str, str]] = {}
    for ref in refs:
        asset = data_repo.get_asset_by_any_id(profile, ref)
        if asset is None:
            continue
        entry = _ref_meta_entry(asset)
        if entry:
            meta[ref] = entry
    if meta:
        payload["ref_meta"] = meta


def _ref_meta_entry(asset: AssetLookup) -> dict[str, str]:
    """Build the ``display_name``/``local_path`` metadata entry for one catalog asset."""
    entry: dict[str, str] = {}
    name = asset.metadata_json.get("display_name")
    if isinstance(name, str) and name:
        entry["display_name"] = name
    for local_file in asset.local_files:
        if (path := verified_local_path(local_file)) is not None:
            entry["local_path"] = str(path)
            entry["local_sha256"] = local_file.sha256 or ""
            break
    return entry


def _resolve_payload_refs(
    data_repo: DataRepository,
    profile: str,
    payload: dict[str, Any],
    task_type: str,
) -> dict[str, Any] | None:
    """Resolve media-id refs in ``payload`` in place, by task type.

    I2V start/end frame refs retain their UUID identity and gain catalog picker
    metadata. R2V ``refs`` are merged into ``reference_images`` for local upload.
    Image task types: refs are *enriched* with
    display_name/local_path so the transport selects the existing asset in the
    picker (see _enrich_image_refs). Returns an error envelope on the first
    unresolvable VIDEO UUID, else ``None`` (image enrichment never errors).
    """
    if task_type not in _VIDEO_TASK_TYPES:
        _enrich_image_refs(data_repo, profile, payload)
        return None
    if task_type == "i2v":
        for ref_key in ("start_image_ref", "end_image_ref"):
            ref_id = payload.get(ref_key)
            if ref_id is None:
                continue
            asset = data_repo.get_asset_by_flow_media_id(profile, ref_id)
            if asset is None:
                return _bad_param(
                    "Reference Not Found",
                    f"'{ref_id}' was not found in your asset catalog for profile "
                    f"{profile!r}. Generate the image first, or pass a local file path.",
                )
            if asset.kind is not AssetKind.IMAGE:
                return _bad_param(
                    "Reference Not Usable",
                    f"'{ref_id}' is not an image asset and cannot be an I2V frame.",
                )
            entry = _ref_meta_entry(asset)
            if not entry:
                return _bad_param(
                    "Reference Not Usable",
                    f"'{ref_id}' has neither a catalog display name nor a verified "
                    "local image fallback.",
                )
            if display_name := entry.get("display_name"):
                payload[f"{ref_key}_display_name"] = display_name
            if local_path := entry.get("local_path"):
                payload[f"{ref_key}_local_path"] = local_path
                payload[f"{ref_key}_local_sha256"] = entry["local_sha256"]
        return None
    if "refs" in payload:
        resolved_paths: list[str] = []
        for ref in payload["refs"]:
            path, err = _resolve_ref_local_path(data_repo, profile, ref)
            if err is not None:
                return err
            # path is never None when err is None (see _resolve_ref_local_path).
            assert path is not None
            resolved_paths.append(path)
        payload["reference_images"] = list(payload.get("reference_images", [])) + resolved_paths
        del payload["refs"]
    return None


def _validate_project(project: str | None) -> dict[str, Any] | None:
    """Return a bad-parameter error dict if ``project`` is set but not a valid
    Flow project id, else ``None``. Reuses the CLI's ``_FLOW_ID_RE`` so the MCP
    ``project`` arg is validated identically to the CLI ``--project`` flag.
    """
    if project is not None and not _FLOW_ID_RE.fullmatch(project):
        return _bad_param(
            "Invalid Project Id",
            f"Project id '{project}' is not a valid Flow project id.",
        )
    return None


def _resolve_image_path(
    raw: str, *, title: str, label: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve a user-supplied image path.

    Returns ``(resolved_path, None)`` when ``raw`` is an existing file, or
    ``(None, error_dict)`` with an RFC 9457 bad-parameter error otherwise.
    Shared by the image and video tools so the validation message stays uniform.
    """
    path = Path(raw).resolve()
    if not path.is_file():
        return None, _bad_param(title, f"{label} '{raw}' does not exist or is not a file.")
    return str(path), None


def _resolve_image_references(
    reference_images: list[str],
) -> tuple[dict[str, list[str]] | None, dict[str, Any] | None]:
    """Split image ``reference_images`` into Flow-media-id refs vs resolved
    on-disk paths. Returns ``({"refs", "ref_paths"}, None)`` or ``(None, error)``.
    """
    refs: list[str] = []
    ref_paths: list[str] = []
    for ref in reference_images:
        if is_media_uuid(ref):
            refs.append(ref)
            continue
        resolved, err = _resolve_image_path(
            ref, title="Invalid Reference Image", label="Reference image path"
        )
        if err is not None:
            return None, err
        assert resolved is not None
        ref_paths.append(resolved)
    return {"refs": refs, "ref_paths": ref_paths}, None


def _build_video_media_inputs(
    *,
    mode: str,
    initial_frame: str | None,
    end_frame: str | None,
    reference_images: list[str] | None,
    reference_entities: list[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate + resolve the media inputs (start/end/reference frames) for a
    video request. Returns ``(payload_fragment, None)`` or ``(None, error)``.

    Enforces mutual exclusivity (r2v refs vs i2v frames) and the mode-specific
    required inputs at the tool boundary, so a missing frame fails fast with a
    clear 400 instead of a cryptic worker ``ValueError``.
    """
    if reference_images and (initial_frame or end_frame):
        return None, _bad_param(
            "Mutually Exclusive Arguments",
            "reference_images (for r2v) cannot be used alongside initial_frame or "
            "end_frame (for i2v).",
        )
    if mode == "i2v" and initial_frame is None:
        return None, _bad_param(
            "Missing Start Image", "i2v (image-to-video) requires 'initial_frame'."
        )
    # A saved CHARACTER entity is a reference in its own right: GenerateVideoRequest
    # accepts "reference_images, ref_names, OR reference_entities" for r2v, so this
    # guard must not be stricter than the domain rule it fronts (#689).
    if mode == "r2v" and not reference_images and not reference_entities:
        return None, _bad_param(
            "Missing References",
            "r2v (reference-to-video) requires 'reference_images' or 'reference_entities'.",
        )

    media: dict[str, Any] = {}
    for frame, ref_key, path_key, noun in (
        (initial_frame, "start_image_ref", "start_image", "Start"),
        (end_frame, "end_image_ref", "end_image", "End"),
    ):
        if frame is None:
            continue
        if is_media_uuid(frame):
            media[ref_key] = frame
            continue
        resolved, err = _resolve_image_path(
            frame, title=f"Invalid {noun} Image", label=f"{noun} image path"
        )
        if err is not None:
            return None, err
        media[path_key] = resolved
    if reference_images:
        ref_data, err = _resolve_image_references(reference_images)
        if err is not None:
            return None, err
        assert ref_data is not None
        if ref_data["ref_paths"]:
            media["reference_images"] = ref_data["ref_paths"]
        if ref_data["refs"]:
            media["refs"] = ref_data["refs"]
    return media, None


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@server.tool(
    name="gflow_generate_image",
    description=(
        "Generate an image using Google Flow's Imagen model. "
        "Produces 1-4 images from a text prompt. "
        "Models: nano2 (fast), nano2-lite (lightweight), nano-pro (balanced), "
        "image4 (highest quality). "
        "Aspects: 1:1, 9:16, 16:9, 4:3, 3:4. "
        "The prompt supports @AssetName mentions to tag saved project characters/assets by name "
        "(resolves to referenceEntities/referenceImages). Reference a SAVED named asset via "
        "@Name; reference an arbitrary one-off image via reference_images. See "
        "docs/REFERENCE_STRATEGIES.md. "
        "On accounts served from flow.google.com, use an existing project and local "
        "reference files and owned image/entity references with fresh weighted preflight. "
        "aspect=auto derives the nearest supported ratio from the first local image or "
        "fresh owned native image UUID dimensions in an explicit project. "
        "Image4 is refused before submit on that composer; retrying will not clear it. "
        "Returns local file paths to the generated images."
    ),
)
@_guarded
async def gflow_generate_image(
    prompt: str,
    model: str = "nano2",
    aspect: str = "1:1",
    count: int = 1,
    seed: int | None = None,
    reference_images: list[str] | None = None,
    reference_syntax: str = "names",
    reference_entities: list[str] | None = None,
    reference_entity_names: list[str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    profile: str = _DEFAULT_PROFILE,
    project: str | None = None,
    project_name: str | None = None,
    instructions: list[str] | None = None,
    ui_mode: str | None = None,
    output: str | None = None,
    wait: bool = True,
) -> dict[str, Any]:
    """Generate an image via Google Flow's Imagen.

    Args:
        prompt: The text prompt describing the desired image. Supports ``@AssetName``
            mentions to tag a saved project character or media asset by name (resolves to
            referenceEntities / referenceImages, deduped against reference_images). Use
            ``@Name`` for a saved named asset; use ``reference_images`` for an arbitrary
            one-off image. See ``docs/REFERENCE_STRATEGIES.md``.
        model: Model to use — 'nano2', 'nano2-lite', 'nano-pro', or 'image4'.
        aspect: Aspect ratio — '1:1', '9:16', '16:9', '4:3', '3:4', or 'auto'.
            Auto derives the nearest supported ratio from the first local PNG/JPEG
            or fresh owned native image UUID dimensions before queueing. UUID refs
            require an explicit project; absent image references refuse Auto.
            This is a local approximation, not Google Auto.
        count: Number of images to generate (1-4).
        seed: Optional native flow.google.com seed (0 through 2147483647-count+1).
            Count outputs use seed+index; returned seeds are verified. Unsupported
            host/transport paths reject before submission; identical pixels are not guaranteed.
        reference_images: Optional list of reference images for image-to-image generation.
            Can be local file paths or owned native image UUIDs.
            Slots mode preserves original order for mixed local/native inputs.
        reference_syntax: names preserves saved @AssetName expansion (default).
            slots uses ordered @reference_N/@character_N, leaves unknown literals
            unchanged and requires native positional materialization.
        reference_entities: Saved Flow CHARACTER entity **ids** to attach
            (mirrors the CLI ``--reference-entity``). Same wire as an ``@Name``
            mention (``referenceEntities``) and dedupes against it; use ids when
            a display name would be ambiguous, since names are not unique.
        reference_entity_names: Optional display names paired positionally with
            ``reference_entities`` (mirrors ``--reference-entity-name``).
        tools: Optional list of prompt tools to apply before generation.
            Each item is ``{"name": str, "options": dict}``.  Valid names
            include ``"creative-director"`` (which supports an ``options``
            key of ``"style"`` for domain-vocabulary injection).
            Requires an OpenAI-compatible endpoint (GFLOW_CLI_LLM_API_KEY
            and/or GFLOW_CLI_LLM_BASE_URL); degrades gracefully to the
            original prompt when unavailable (mirrors the CLI ``--tool/-t``
            flag).
        profile: gflow-cli profile name to use.  Leave as ``"default"`` (or
            omit) to auto-resolve using the same precedence as the CLI:
            ``GFLOW_CLI_PROFILE`` env var → ``config.toml`` default →
            auto-select if exactly one profile exists.
        project: Optional existing Flow project id to generate into (mirrors the
            CLI ``--project`` flag). When omitted, a fresh project is created —
            on labs.google or flow.google.com, whichever serves the account.
        project_name: Optional human-readable project title to use when creating a
            fresh Flow project.
        instructions: Optional list of custom agent instructions to add or enable
            (only in agentic mode).
        ui_mode: Required Flow UI arm — 'classic' (hard aspect controls),
            'agentic' (chat surface; forced automatically when instructions are
            given), or 'auto' (bind whatever renders, the default). If the arm
            can't be reached, generation aborts before submitting (no credits).
            Overrides GFLOW_CLI_UI_MODE.

    Returns:
        Dict with 'status', 'files' (list of local file paths), and metadata.
        On failure, 'status' is 'failed' or 'error' with an RFC 9457 'error' dict.
    """
    aspect_metadata: dict[str, str] = {}
    requested_aspect = aspect
    native_auto_id: str | None = None
    if aspect == "auto":
        ordered_refs: list[Path | ImageRef] = []
        if reference_images:
            validated, error = _resolve_image_references(reference_images)
            if error is not None:
                return error
            assert validated is not None
            first = reference_images[0]
            ordered_refs = (
                [ImageRef(first)] if is_media_uuid(first) else [Path(validated["ref_paths"][0])]
            )
        if ordered_refs and isinstance(ordered_refs[0], ImageRef):
            if not project:
                return _bad_param(
                    "Native Auto requires project", "Supply the existing image project UUID"
                )
            native_auto_id = ordered_refs[0].name
            aspect = "16:9"  # Internal placeholder; always resolved before queue/submit.
        else:
            try:
                _, decision = resolve_image_aspect(aspect, ordered_refs)
            except ConfigurationError as exc:
                return {"status": "error", "error": _gflow_error_dict(exc)}
            assert decision is not None
            aspect = decision.resolved_aspect
            aspect_metadata = aspect_decision_metadata(decision)
    image_slot_payload: dict[str, Any] = {}
    if reference_syntax not in {"names", "slots"}:
        return _bad_param("Invalid reference syntax", "reference_syntax must be names or slots")
    if reference_syntax == "slots":
        from gflow_cli.worker.codec import build_image_request

        preflight_refs: dict[str, Any] = {"refs": [], "ref_paths": []}
        if reference_images:
            resolved_refs, error = _resolve_image_references(reference_images)
            if error is not None:
                return error
            assert resolved_refs is not None
            preflight_refs = resolved_refs
        try:
            from gflow_cli.api.reference_markers import (
                prepare_explicit_image_inputs,
                reference_plan_record,
            )

            base = build_image_request(
                {
                    "prompt": prompt,
                    "model": model,
                    "count": count,
                    "reference_entities": reference_entities or [],
                    **preflight_refs,
                }
            )
            local_paths = iter(preflight_refs["ref_paths"])
            ordered = [
                ImageRef(value) if is_media_uuid(value) else Path(next(local_paths))
                for value in reference_images or []
            ]
            prepared = prepare_explicit_image_inputs(base, ordered)
            assert prepared.reference_prompt_plan is not None
            image_slot_payload = {
                "local_ref_ids": list(prepared.local_ref_ids),
                "reference_prompt_plan": reference_plan_record(prepared.reference_prompt_plan),
            }
        except (ValueError, TypeError) as exc:
            return _bad_param("Invalid image reference slots", str(exc))
    if seed is not None:
        try:
            GenerateImageRequest(prompt=prompt, count=count, seed=seed)
        except ValueError as error:
            return _bad_param("Invalid image seed", str(error))
    if (proj_err := _validate_project(project)) is not None:
        return proj_err

    if ui_mode is not None:
        # Normalize case to mirror the CLI's click.Choice(case_sensitive=False)
        # and answer with the same _bad_param RFC 9457 envelope the video tool
        # uses — this branch previously returned a flat ``error`` string, which
        # crashes any client reading ``error["title"]`` (see the sibling
        # rejection in gflow_generate_video).
        ui_mode = ui_mode.lower()
        if ui_mode not in {m.value for m in UiMode}:
            return _bad_param(
                "Invalid ui_mode",
                f"Expected one of {[m.value for m in UiMode]}, got {ui_mode!r}.",
            )

    if not await _rate_limiter.acquire():
        log.warning("mcp.tool.rate_limited", tool="gflow_generate_image")
        return _rate_limited_envelope()

    # Resolve and validate the profile BEFORE acquiring the per-profile lock so
    # that the lock key matches the real on-disk profile name, not the sentinel.
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved  # profile error — bail out early
    resolved_profile = resolved
    if native_auto_id is not None:
        assert project is not None
        settings = get_settings()
        async with _profile_lock(resolved_profile):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved_profile), headless=settings.headless
            ) as client:
                _, decision = await client.resolve_native_image_aspect(project, native_auto_id)
        aspect = decision.resolved_aspect
        aspect_metadata = aspect_decision_metadata(decision)

    log.info(
        "mcp.tool.generate_image",
        prompt=prompt[:80],
        model=model,
        aspect=aspect,
        count=count,
        profile=resolved_profile,
    )

    # Validate + adapt the agent-supplied tools array to CLI --tool specs.
    adapted = _adapt_tools(tools)
    if isinstance(adapted, dict):
        return adapted
    tool_specs = adapted

    payload: dict[str, Any] = {
        "prompt": prompt,
        "model": model,
        "aspect": aspect,
        "count": count,
    }
    if aspect_metadata:
        payload["aspect_decision"] = aspect_metadata
    if reference_syntax == "slots":
        payload["reference_syntax"] = reference_syntax
        payload.update(image_slot_payload)
    if instructions:
        payload["instructions"] = list(instructions)
    if ui_mode is not None:
        payload["ui_mode"] = ui_mode
    if seed is not None:
        payload["seed"] = seed
    if project is not None:
        payload["project_id"] = project
    if project_name is not None:
        payload["project_name"] = project_name
    if output is not None:
        payload["output_file"] = output
    # Omitted rather than written empty when unused: `codec.build_image_request`
    # already reads both keys, so an empty list is a real (and wrong) instruction.
    if reference_entities:
        payload["reference_entities"] = list(reference_entities)
    if reference_entity_names:
        payload["reference_entity_names"] = list(reference_entity_names)

    task_type = "t2i"
    if reference_images:
        ref_data, err = _resolve_image_references(reference_images)
        if err is not None:
            return err
        assert ref_data is not None
        payload["refs"] = ref_data["refs"]
        payload["ref_paths"] = ref_data["ref_paths"]
        task_type = "i2i"

    if tool_specs:
        payload["tool_specs"] = list(tool_specs)

    result = await _run_generation_task(
        profile=resolved_profile,
        task_type=task_type,
        payload=payload,
        wait=wait,
    )

    result.update(aspect_metadata)

    # Annotate the result with the original request parameters for context.
    result["params"] = {
        "prompt": prompt,
        "model": model,
        "aspect": requested_aspect,
        "count": count,
        "seed": seed,
        "reference_images": reference_images,
        "tools": tools or [],
        "tool_specs": list(tool_specs),
        "profile": resolved_profile,
        "requested_profile": profile,
        "project": project,
    }
    return result


def _build_video_payload(
    prompt: str,
    mode: str,
    aspect: str,
    count: int,
    model: str | None,
    duration: int | None,
    resolution: str | None,
    tool_specs: Any,
    project: str | None,
    project_name: str | None,
    output: str | None = None,
    ui_mode: str | None = None,
    reference_entities: list[str] | None = None,
    reference_entity_names: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "mode": mode,
        "aspect": aspect,
        "count": count,
    }
    if ui_mode is not None:
        payload["ui_mode"] = ui_mode
    if model is not None:
        payload["model"] = model
    if duration is not None:
        payload["duration"] = duration
    if resolution is not None:
        payload["resolution"] = resolution
    if tool_specs:
        payload["tool_specs"] = list(tool_specs)
    if project is not None:
        payload["project_id"] = project
    if project_name is not None:
        payload["project_name"] = project_name
    if output is not None:
        payload["output_file"] = output
    # Omitted rather than written empty when unused: `codec.build_video_request`
    # already reads both keys, so an empty list is a real (and wrong) instruction.
    if reference_entities:
        payload["reference_entities"] = list(reference_entities)
    if reference_entity_names:
        payload["reference_entity_names"] = list(reference_entity_names)
    return payload


@server.tool(
    name="gflow_generate_video",
    description=(
        "Generate a video using Google Flow's Veo model. "
        "Modes: t2v (text-to-video), i2v (image-to-video), r2v (reference-to-video). "
        "Aspects: 9:16, 16:9. "
        "Optional model (veo_lite/veo_fast/veo_quality/omni_flash), duration (seconds), "
        "and count select the Veo model, clip length, and batch size (CLI parity). "
        "The prompt supports @CharacterName mentions to tag saved project characters by name "
        "(resolves to referenceEntities). Reference a SAVED character via @Name; pass one-off "
        "ingredient images via reference_images. See docs/REFERENCE_STRATEGIES.md. "
        "Optional ui_mode ('classic'/'auto') verifies the classic editor pre-submit and aborts "
        "before spending credits if unreachable; 'agentic' is not supported for video. "
        "Returns the local file path to the generated video."
    ),
)
@_guarded
async def gflow_generate_video(  # NOSONAR
    prompt: str,
    mode: str = "t2v",
    aspect: str = "9:16",
    initial_frame: str | None = None,
    end_frame: str | None = None,
    reference_images: list[str] | None = None,
    reference_entities: list[str] | None = None,
    reference_entity_names: list[str] | None = None,
    model: str | None = None,
    duration: int | None = None,
    resolution: str | None = None,
    count: int = 1,
    tools: list[dict[str, Any]] | None = None,
    profile: str = _DEFAULT_PROFILE,
    project: str | None = None,
    project_name: str | None = None,
    ui_mode: str | None = None,
    output: str | None = None,
    wait: bool = True,
    captcha_order: str | None = None,
    captcha_retry: StrictInt | None = None,
    captcha_token: str | None = None,
) -> dict[str, Any]:
    """Generate a video via Google Flow's Veo.

    Args:
        prompt: The text prompt describing the desired video. Supports ``@CharacterName``
            mentions to tag a saved project character by name (resolves to referenceEntities).
            Use ``@Name`` for a saved character; use ``reference_images`` for one-off ingredient
            images. See ``docs/REFERENCE_STRATEGIES.md``.
        mode: Generation mode — 't2v', 'i2v', or 'r2v'.
        aspect: Aspect ratio — '9:16' or '16:9'.
        initial_frame: Path to start frame image (required for i2v). On an
            account Google has moved to flow.google.com a **local file** is the
            only form served there — uploaded through the editor, then bound from
            the Frames picker under a **run-unique** name (``hero.png`` is listed
            as ``hero-<8 hex>.png``), so a re-run of the same file cannot bind an
            earlier upload (#792); a Flow media UUID returns the
            exit-36-equivalent envelope.
        end_frame: Path to end frame image (optional for i2v). Local files are
            driven on flow.google.com; UUID/@Name refs return the
            exit-36-equivalent envelope on a moved account.
        reference_images: List of reference image paths (ingredients) for r2v.
        reference_entities: Saved Flow CHARACTER entity **ids** to attach
            (mirrors the CLI ``--reference-entity``). Same wire as an
            ``@Name`` mention (``referenceEntities``) and dedupes against it;
            use ids when a display name would be ambiguous, since names are
            not unique. Satisfies r2v's reference requirement on its own.
        reference_entity_names: Optional display names paired positionally with
            ``reference_entities`` (mirrors ``--reference-entity-name``); used
            only to filter the picker, the ids remain the identity.
        model: Optional Veo model — 'veo_lite', 'veo_fast', 'veo_quality',
            'omni_flash' (aliases accepted, mirrors the CLI ``--model``). When
            omitted, Flow's UI default applies EXCEPT for i2v with frames,
            where the transport defaults to veo-lite. Every model supports i2v
            with a start frame and with an end frame; 'omni_flash' was the last
            exception and its end-frame route was wire-verified 2026-09-02
            (refs #125, #626).
        duration: Optional clip length in seconds (mirrors the CLI ``--duration``):
            4/6/8 on the Veo 3.1 models, 4/6/8/10 on ``omni_flash``; whether the
            account's cohort renders the control is decided pre-submit at zero cost.
            When omitted, Flow's per-model default applies. On the migrated
            flow.google.com host an 'r2v' request accepts only 8 and pins it when
            omitted — Flow offers reference-to-video at its base tier alone, and at
            4 or 6 it drops the references and bills a text-to-video clip instead of
            refusing; any other value returns the exit-11-equivalent envelope.
        resolution: Optional video resolution — '360p' or '720p' (omni-flash only,
            mirrors the CLI ``--resolution``). When omitted, Flow's default applies. On any
            other model, or on the labs editor, the job fails pre-submit with the
            exit-11-equivalent envelope and no credits spent.
        count: Number of videos to generate (mirrors the CLI ``--count``; default 1).
        tools: Optional list of prompt tools to apply before generation.
            Each item is ``{"name": str, "options": dict}``.  Valid names
            include ``"creative-director"`` (which supports an ``options``
            key of ``"style"`` for domain-vocabulary injection).
            Requires an OpenAI-compatible endpoint (GFLOW_CLI_LLM_API_KEY
            and/or GFLOW_CLI_LLM_BASE_URL); degrades gracefully to the
            original prompt when unavailable (mirrors the CLI ``--tool/-t``
            flag on ``video t2v``).
        profile: gflow-cli profile name to use.  Leave as ``"default"`` (or
            omit) to auto-resolve using the same precedence as the CLI:
            ``GFLOW_CLI_PROFILE`` env var → ``config.toml`` default →
            auto-select if exactly one profile exists.
        project: Optional existing Flow project id to generate into (mirrors the
            CLI ``--project`` flag on ``video t2v``/``i2v``/``r2v``). When
            omitted, a fresh project is created (titled ``project_name`` when
            given) on labs.google or flow.google.com, whichever serves the
            account. On an account served flow.google.com (``GFLOW_CLI_FLOW_HOST``,
            read from the server/daemon environment, not per call) the ported
            modes are 't2v'; 'i2v' with a local ``initial_frame`` with or without
            a local ``end_frame``; and 'r2v' with local ``reference_images``. A UUID
            frame, an end frame by UUID/``@Name``, and r2v by ``ref_names`` or
            ``reference_entities`` return the exit-36-equivalent envelope.
        ui_mode: Required Flow UI arm (mirrors the CLI ``--ui-mode`` on
            ``video t2v``/``i2v``; applies to every mode of this tool,
            including 'r2v'). Video generation only has a classic driver:
            'classic'/'auto' verify the classic editor pre-submit (best-effort
            DOM probe) and abort before spending credits if it is unreachable;
            'agentic' is not yet supported for video and is rejected (400).
        **kwargs: Additional optional keyword arguments such as ``project_name``.

    Returns:
        Dict with 'status', 'files' (list of local file paths), and metadata.
        On failure, 'status' is 'failed' or 'error' with an RFC 9457 'error' dict.
    """
    from gflow_cli.selfhost.video_captcha_policy import validate_video_captcha_controls

    controls = {
        **({"captchaOrder": captcha_order} if captcha_order is not None else {}),
        **({"captchaRetry": captcha_retry} if captcha_retry is not None else {}),
        **({"captcha_token": captcha_token} if captcha_token is not None else {}),
    }
    try:
        validate_video_captcha_controls({"count": count, **controls}, project, queued=True)
    except ValueError as exc:
        return _bad_param("Invalid Video CAPTCHA Controls", str(exc))

    if (proj_err := _validate_project(project)) is not None:
        return proj_err

    if ui_mode is not None:
        # Normalize case to mirror the CLI's click.Choice(case_sensitive=False);
        # both invalid branches answer with the same _bad_param RFC 9457
        # envelope as every other 400 from this tool (a flat-string error
        # would crash clients reading error["title"]).
        ui_mode = ui_mode.lower()
        if ui_mode not in {m.value for m in UiMode}:
            return _bad_param(
                "Invalid ui_mode",
                f"Expected one of {[m.value for m in UiMode]}, got {ui_mode!r}.",
            )
        if ui_mode == UiMode.AGENTIC.value:
            # #299: no agentic VIDEO driver exists — mirror the CLI edge's
            # rejection instead of an exit-28 whose retry hint would mislead.
            return _bad_param(
                "Unsupported ui_mode for video",
                "ui_mode 'agentic' is not supported for video generation yet "
                "(no agentic video driver exists; refs #299). Use 'classic' "
                "or 'auto'.",
            )

    from gflow_cli.api.video import I2V_DEFAULT_MODEL, VideoModel, validate_duration_for_model

    # Validate the model alias up front (mirrors the CLI's pre-spend check) so an
    # unknown model fails fast with a 400 instead of dying deep in the worker.
    if model is not None:
        try:
            VideoModel.from_cli(model)
        except ValueError as exc:
            return _bad_param("Invalid Video Model", str(exc))

    # Centralized duration validation: validate_duration_for_model rejects an
    # invalid duration before queuing the job so the agent gets a clean 400
    # instead of a ValueError inside the worker. Mirrors the CLI's pre-spend
    # checks: i2v binds I2V_DEFAULT_MODEL when `model` is omitted (so "no model"
    # is not "no opinion" there), while t2v/r2v inherit Flow's sticky UI default,
    # which is unknowable here and left unguarded by design.
    if duration is not None:
        # #659: the CLI's --duration is a click.Choice, so 99 never reaches the
        # transport there; here it did, and queued a browser run that died at claim.
        if duration not in VIDEO_DURATION_CHOICES:
            return _bad_param(
                "Unsupported duration",
                f"duration must be one of {list(VIDEO_DURATION_CHOICES)} seconds; got {duration}",
            )
        effective = VideoModel.from_cli(model) if model is not None else None
        if effective is None and mode == "i2v" and (initial_frame or end_frame):
            effective = I2V_DEFAULT_MODEL
        if effective is not None:
            try:
                validate_duration_for_model(effective, duration)
            except ValueError as exc:
                return _bad_param(
                    "Unsupported duration for model",
                    str(exc),
                )

    if not await _rate_limiter.acquire():
        log.warning("mcp.tool.rate_limited", tool="gflow_generate_video")
        return _rate_limited_envelope()

    # Resolve and validate the profile BEFORE acquiring the per-profile lock so
    # that the lock key matches the real on-disk profile name, not the sentinel.
    resolved_profile = _resolve_and_validate_profile(profile)
    if isinstance(resolved_profile, dict):
        return resolved_profile  # profile error — bail out early

    log.info(
        "mcp.tool.generate_video",
        prompt=prompt[:80],
        mode=mode,
        aspect=aspect,
        profile=resolved_profile,
    )

    adapted = _adapt_tools(tools)
    if isinstance(adapted, dict):
        return adapted
    tool_specs = adapted

    media, media_err = _build_video_media_inputs(
        mode=mode,
        initial_frame=initial_frame,
        end_frame=end_frame,
        reference_images=reference_images,
        reference_entities=reference_entities,
    )
    if media_err is not None:
        return media_err
    assert media is not None

    payload = _build_video_payload(
        prompt=prompt,
        mode=mode,
        aspect=aspect,
        count=count,
        model=model,
        duration=duration,
        resolution=resolution,
        tool_specs=tool_specs,
        project=project,
        project_name=project_name,
        output=output,
        ui_mode=ui_mode,
        reference_entities=reference_entities,
        reference_entity_names=reference_entity_names,
    )
    payload.update(media)
    payload.update(controls)

    # task_type matches the mode ("t2v", "i2v", "r2v")
    result = await _run_generation_task(
        profile=resolved_profile,
        task_type=mode,
        payload=payload,
        wait=wait,
    )

    # Annotate the result with the original request parameters for context.
    result["params"] = {
        "prompt": prompt,
        "mode": mode,
        "aspect": aspect,
        "initial_frame": initial_frame,
        "end_frame": end_frame,
        "reference_images": reference_images or [],
        "model": model,
        "duration": duration,
        "resolution": resolution,
        "count": count,
        "tools": tools or [],
        "tool_specs": list(tool_specs),
        "profile": resolved_profile,
        "requested_profile": profile,
        "project": project,
        "project_name": project_name,
    }
    return result


@server.tool(
    name="gflow_list_tools",
    description="List available gflow prompt tools (name, title, description, category).",
)
@_guarded
async def gflow_list_tools() -> dict[str, Any]:
    """List available prompt tools that can be passed to gflow_generate_image/video.

    Returns:
        Dict with 'tools' list; each entry has name, title, description, category.
    """
    from gflow_cli.tools.registry import iter_tools

    return {
        "tools": [
            {"name": s.name, "title": s.title, "description": s.description, "category": s.category}
            for s in iter_tools()
        ]
    }


@server.tool(
    name="gflow_get_credits",
    description=(
        "Read the current Google Flow credit balance for one saved profile or all profiles. "
        "This is read-only and spends no credits. Set all_profiles=true when choosing an "
        "account for generation; partial profile failures remain visible in the result."
    ),
)
@_guarded
async def gflow_get_credits(
    profile: str = _DEFAULT_PROFILE,
    all_profiles: bool = False,
) -> dict[str, Any]:
    """Inspect current Flow credits through the shared CLI service."""

    if all_profiles:
        return await inspect_all_credit_profiles()
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    async with _profile_lock(resolved):
        return await inspect_credit_profile(resolved)


def _character_to_dict(char: Any) -> dict[str, Any]:
    """Serialise a Character for the wire.

    Mirrors `Character`'s own rule: only stable identifiers. Signed CDN URLs
    (``fifeUrl``, ``thumbnailUrl``) are excluded upstream so persisted or logged data
    never carries credential-bearing URLs, and this must not reintroduce them.
    """
    return {
        "entity_id": char.entity_id,
        "display_name": char.display_name,
        "project_id": char.project_id,
        "workflow_ids": list(char.workflow_ids),
        "voice": char.voice,
        "personality": char.personality,
        "thumbnail_media_id": char.thumbnail_media_id,
    }


@server.tool(
    name="gflow_character_create_from_images",
    description=(
        "Create a native Flow character by copying one or two existing owned image IDs. "
        "Portrait/body slots are 0/1; originals remain active. No portrait generation or credits. "
        "Direct bounded operation, not queued; inspect partial identity before retrying."
    ),
)
@_guarded
async def gflow_character_create_from_images(
    project: str,
    display_name: str,
    image_reference_1: str,
    image_reference_2: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Copy owned images into a native character without generating a portrait.

    Args:
        project: Owning project UUID.
        display_name: Character name, 1–200 characters.
        image_reference_1: Existing owned image media UUID (portrait).
        image_reference_2: Optional existing owned image media UUID (body).
        personality: Optional notes, at most 2000 characters.
        voice: Optional system preset; case-insensitive, no custom synthesis.
        profile: Saved profile name.
    """
    voice = normalize_preset_voice(voice)
    validate_create_inputs(
        project, display_name, image_reference_1, image_reference_2, personality, voice
    )
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    async with _profile_lock(resolved):
        char = await native_create_character_from_images(
            profile=resolved,
            project_id=project,
            display_name=display_name,
            image_reference_1=image_reference_1,
            image_reference_2=image_reference_2,
            personality=personality,
            voice=voice,
        )
    return {"status": "ok", "project": project, "character": _character_to_dict(char)}


@server.tool(
    name="gflow_character_update",
    description=(
        "Change native character name, notes or system preset metadata without generation. "
        "No credits; empty personality clears notes. Direct bounded operation, not queued; "
        "an unknown outcome is non-retryable and must be inspected."
    ),
)
@_guarded
async def gflow_character_update(
    project: str,
    entity_id: str,
    display_name: str | None = None,
    personality: str | None = None,
    voice: str | None = None,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Update an existing owned native character.

    Args:
        project: Owning project UUID.
        entity_id: Existing owned character UUID.
        display_name: Optional new name, 1–200 characters.
        personality: Optional new notes, at most 2000 characters; empty clears.
        voice: Optional system preset; case-insensitive, no custom synthesis.
        profile: Saved profile name.
    """
    voice = normalize_preset_voice(voice)
    validate_update_inputs(project, entity_id, display_name, personality, voice)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    async with _profile_lock(resolved):
        char = await native_update_character(
            profile=resolved,
            project_id=project,
            entity_id=entity_id,
            display_name=display_name,
            personality=personality,
            voice=voice,
        )
    return {"status": "ok", "project": project, "character": _character_to_dict(char)}


@server.tool(
    name="gflow_character_rm",
    description=(
        "Permanently remove an owned Flow character. Requires explicit confirm_delete=true. "
        "Pre-reads ownership/name before deleting. No credits, direct operation, no replay; "
        "inspect an unconfirmed outcome before any explicit retry."
    ),
)
@_guarded
async def gflow_character_rm(
    project: str,
    entity_id: str | None = None,
    name: str | None = None,
    confirm_delete: bool = False,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Remove one character only after an explicit deletion confirmation.

    Args:
        project: Owning project UUID.
        entity_id: Existing owned character UUID; mutually exclusive with name.
        name: Exact display name; ambiguous names are refused.
        confirm_delete: Must be true to authorize permanent deletion.
        profile: Saved profile name.
    """
    if confirm_delete is not True:
        return _bad_param(
            "Deletion confirmation required", "Set confirm_delete=true to remove this character."
        )
    validate_character_selector(project, entity_id, name)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client,
    ):
        char = await client.get_character(project, entity_id=entity_id, name=name)
        await client.delete_characters(project, [char.entity_id])
    return {
        "status": "ok",
        "project": project,
        "deleted": {"entity_id": char.entity_id, "display_name": char.display_name},
    }


@server.tool(
    name="gflow_character_list",
    description=(
        "List the saved Flow CHARACTER entities in a project, with their entity ids. "
        "Read-only and spends no credits. Call this to discover what you can attach: "
        "an id goes to reference_entities on the generate tools, and a display_name can "
        "be used as an @Name mention in a prompt (same wire, they dedupe). "
        "Drives a browser session, so it is slower than the catalog tools."
    ),
)
@_guarded
async def gflow_character_list(
    project: str,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """List a project's Flow Character entities.

    Args:
        project: Flow project id to enumerate (mirrors the CLI ``--project``).
        profile: gflow-cli profile name; resolves like the CLI when left as "default".

    Returns:
        ``{"status": "ok", "characters": [...], "count": N}``. The list is exactly what
        Flow returned -- an empty list means the project has none, never that the lookup
        was skipped (#499).
    """
    log.info("mcp.tool.character_list", project=project, profile=profile)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved

    settings = get_settings()
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=settings.profile_subdir(resolved),
            headless=settings.headless,
        ) as client,
    ):
        chars = await client.list_characters(project)

    return {
        "status": "ok",
        "project": project,
        "characters": [_character_to_dict(c) for c in chars],
        "count": len(chars),
    }


@server.tool(
    name="gflow_character_voices",
    description=(
        "List system preset voices. Default bundled lookup is offline; catalog google requires "
        "an owned project and opens a read-only browser session without generation. Choose "
        "a valid voice name."
    ),
)
@_guarded
async def gflow_character_voices(
    catalog: str = "bundled", project: str | None = None, profile: str = "default"
) -> dict[str, Any]:
    """List preset Character TTS voices.

    Reads the in-process ``VOICES`` table, so unlike the other character tools it
    opens no Flow session and needs no profile by default. Explicit catalog=google
    requires a project UUID and reads native system presets through the browser.

    Args:
        catalog: bundled stays offline; google reads native system presets.
        project: Required native project UUID for catalog google.
        profile: Profile owning the selected native project.

    Returns:
        Voice name/description/public sample URL and count. Native results also
        identify project_id, catalog, scope, returned_count and complete=None.
    """
    from gflow_cli.api.character import VOICES

    if catalog not in {"bundled", "google"}:
        return _bad_param("Invalid voice catalog", "catalog must be bundled or google")
    if catalog == "google":
        if not is_uuid(project):
            return _bad_param("Invalid native project", "Native project identifier must be a UUID")
        assert project is not None
        resolved = _resolve_and_validate_profile(profile)
        if isinstance(resolved, dict):
            return resolved
        settings = get_settings()
        async with _profile_lock(resolved):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                snapshot = await client.list_native_voices(project)
        return {"status": "ok", "count": snapshot["returned_count"], **snapshot}
    if project is not None:
        return _bad_param("Invalid voice catalog controls", "project requires catalog google")

    return {
        "status": "ok",
        "voices": [
            {"name": v.name, "description": v.description, "sample_url": v.sample_url}
            for v in VOICES
        ],
        "count": len(VOICES),
    }


@server.tool(
    name="gflow_character_show",
    description=(
        "Show one saved Flow CHARACTER entity by id or by exact display name. "
        "Read-only and spends no credits. Exactly one of entity_id or name is required; "
        "an ambiguous name is an error rather than a guess, which is the reason to prefer "
        "the id. Drives a browser session."
    ),
)
@_guarded
async def gflow_character_show(
    project: str,
    entity_id: str | None = None,
    name: str | None = None,
    profile: str = _DEFAULT_PROFILE,
    include_urls: bool = False,
) -> dict[str, Any]:
    """Show one Flow Character by id or exact display name.

    Args:
        project: Flow project id the character belongs to.
        entity_id: The character's entity id (mirrors the CLI ``--id``).
        name: Exact display name (mirrors ``--name``). Case-sensitive, and ambiguous
            names are refused rather than resolved arbitrarily.
        profile: gflow-cli profile name.
        include_urls: Include fresh confidential image/thumbnail URLs; do not persist.

    Returns:
        ``{"status": "ok", "character": {...}}``.
    """
    if (entity_id is None) == (name is None):
        return _bad_param(
            "Ambiguous Character Selector",
            "Provide exactly one of 'entity_id' or 'name'.",
        )
    log.info("mcp.tool.character_show", project=project, by="id" if entity_id else "name")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved

    settings = get_settings()
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=settings.profile_subdir(resolved),
            headless=settings.headless,
        ) as client,
    ):
        if include_urls:
            detail = await client.get_character_detail(project, entity_id=entity_id, name=name)
            return {"status": "ok", "project": project, "character": detail}
        char = await client.get_character(project, entity_id=entity_id, name=name)

    return {"status": "ok", "project": project, "character": _character_to_dict(char)}


@server.tool(
    name="gflow_download_media",
    description=(
        "Fetch an already-generated VIDEO from Flow by its media ID and write it to "
        "disk. For a generation that finished and was billed but whose download failed "
        "— the clip is in the Flow project and the local catalog shows no file for it. "
        "Spends no credits: the generation was already paid for. The bytes are verified "
        "against the size Flow reports before the file is written. Video only: an image "
        "media ID is refused immediately (exit 11) because the signed URL this needs "
        "comes from a record only a clip's route emits. See issue #877. "
        "The transfer already retries a dropped connection internally, so a failure "
        "marked retryable means wait a moment and call again — never immediately, and "
        "never in a tight loop: each call opens a browser under a per-profile lease, and "
        "a second concurrent call fails on that lease instead (exit 11)."
    ),
)
@_guarded
async def gflow_download_media(
    media_id: str,
    out_dir: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Recover an already-generated asset by media id.

    Args:
        media_id: The Flow media ID, as shown by ``gflow_list_projects`` assets or the
            catalog. This is the id a failed-download generation left behind.
        out_dir: Directory to write into. Defaults to the configured output dir.
        profile: Restrict the catalog lookup to one profile. Omit to search all —
            an id present under several profiles is reported as an error naming them.

    Returns:
        Dict with the written ``path``, ``bytes``, ``media_id``, ``workflow_id``,
        ``project_id`` and ``profile``.
    """
    log.info("mcp.tool.download_media", media_id=media_id, profile=profile)
    result = await download_media(
        media_id=media_id,
        profile=profile,
        out_dir=Path(out_dir) if out_dir else None,
    )
    return {
        "status": "ok",
        "media_id": result.media_id,
        "workflow_id": result.workflow_id,
        "profile": result.profile_name,
        "project_id": result.project_id,
        "path": str(result.path),
        "bytes": result.bytes,
    }


@server.tool(
    name="gflow_upscale_image",
    description=(
        "Upscale a platform-generated Flow image to 2K or 4K and save it locally. "
        "media_id is the UUID of the image to upscale. "
        "scale is '2k' or '4k' (4k requires Ultra subscription; Pro/Plus accounts support 2k). "
        "project is optional (resolved from the local catalog when omitted). "
        "out_dir is the output directory (defaults to configured images directory). "
        "profile selects the auth profile (defaults to the active profile). "
        "Spends no credits: image upscale is free."
    ),
)
@_guarded
async def gflow_upscale_image(
    media_id: str,
    scale: str = "2k",
    project: str | None = None,
    out_dir: str | None = None,
    profile: str = _DEFAULT_PROFILE,
    captcha_token: str | None = None,
) -> dict[str, Any]:
    """Upscale a platform-generated image to 2K or 4K.

    Args:
        media_id: The Flow media ID (UUID) of the generated image.
        scale: Target resolution: '2k' or '4k' (4k is Ultra-only).
        project: Project UUID that owns the media. Resolved from local catalog when omitted.
        out_dir: Output directory (defaults to configured images directory).
        profile: Profile name (overrides default).
        captcha_token: Optional single-use native 2K CAPTCHA token.

    Returns:
        Dict with status, media_id, project_id, scale, path, and size bytes.
    """
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved

    try:
        resolution = TargetResolution.from_cli(scale)
    except ValueError as exc:
        return _bad_param("Invalid Scale", str(exc))

    if not is_media_uuid(media_id):
        return _bad_param("Invalid Media ID", f"Media ID {media_id!r} is not a valid UUID")

    if (proj_err := _validate_project(project)) is not None:
        return proj_err

    resolved_project = project or lookup_project_in_catalog(media_id, resolved)
    if not resolved_project:
        return _bad_param(
            "Project Required",
            f"Could not resolve the owning project for media {media_id!r} from the local catalog "
            f"(profile {resolved!r}). Pass project parameter explicitly.",
        )

    settings = get_settings()
    profile_dir = settings.profile_subdir(resolved)
    output_root = Path(out_dir) if out_dir is not None else settings.output_dir
    scale_label = scale.strip().lower()
    from datetime import date

    out_path = output_root / "images" / date.today().isoformat() / f"{media_id}_{scale_label}.png"

    log.info("mcp.tool.upscale_image", media_id=media_id, scale=scale_label, profile=resolved)
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=profile_dir,
            headless=settings.headless,
            out_dir=output_root,
        ) as client,
    ):
        with native_captcha_or_none(
            captcha_token, project_id=resolved_project, action="IMAGE_GENERATION"
        ):
            target = await client.upsample_image(
                media_id=media_id,
                project_id=resolved_project,
                target_resolution=resolution,
                out_path=out_path,
            )

    from gflow_cli.storage import is_cloud_path

    target_path = Path(str(target))
    file_bytes = (
        target_path.stat().st_size if target_path.exists() and not is_cloud_path(target) else 0
    )
    return {
        "status": "ok",
        "media_id": media_id,
        "project_id": resolved_project,
        "scale": scale_label,
        "path": str(target),
        "bytes": file_bytes,
    }


@server.tool(
    name="gflow_upscale_video",
    description=(
        "Upscale or export a platform-generated Flow video to 1080p Full HD (or 270p GIF). "
        "media_id is the UUID of the video to upscale. "
        "scale is '1080p' (Full HD), '720p' (original), or '270p' (animated GIF). "
        "project is optional (resolved from the local catalog when omitted). "
        "out_dir is the output directory (defaults to configured videos directory). "
        "profile selects the auth profile (defaults to the active profile). "
        "Spends no credits: video upscale/export is free."
    ),
)
@_guarded
async def gflow_upscale_video(
    media_id: str,
    scale: str = "1080p",
    project: str | None = None,
    out_dir: str | None = None,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Upscale or export a platform-generated video to 1080p, 720p, or 270p.

    Args:
        media_id: The Flow media ID (UUID) of the generated video.
        scale: Target quality: '1080p' (enhanced), '720p' (original), or '270p' (GIF).
        project: Project UUID that owns the media. Resolved from local catalog when omitted.
        out_dir: Output directory (defaults to configured videos directory).
        profile: Profile name (overrides default).

    Returns:
        Dict with status, media_id, project_id, scale, path, and size bytes.
    """
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved

    scale_label = scale.strip().lower()
    from gflow_cli.api.transports.migrated_video_upscale import VALID_VIDEO_SCALES

    if scale_label not in VALID_VIDEO_SCALES:
        msg = f"Scale must be one of {VALID_VIDEO_SCALES}, got {scale!r}"
        return _bad_param("Invalid Scale", msg)

    if not is_media_uuid(media_id):
        return _bad_param("Invalid Media ID", f"Media ID {media_id!r} is not a valid UUID")

    if (proj_err := _validate_project(project)) is not None:
        return proj_err

    resolved_project = project or lookup_project_in_catalog(media_id, resolved)
    if not resolved_project:
        return _bad_param(
            "Project Required",
            f"Could not resolve the owning project for media {media_id!r} from the local catalog "
            f"(profile {resolved!r}). Pass project parameter explicitly.",
        )

    settings = get_settings()
    profile_dir = settings.profile_subdir(resolved)
    output_root = Path(out_dir) if out_dir is not None else settings.output_dir
    ext = "gif" if scale_label == "270p" else "mp4"
    from datetime import date

    out_path = output_root / "videos" / date.today().isoformat() / f"{media_id}_{scale_label}.{ext}"

    log.info("mcp.tool.upscale_video", media_id=media_id, scale=scale_label, profile=resolved)
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=profile_dir,
            headless=settings.headless,
            out_dir=output_root,
        ) as client,
    ):
        target = await client.upsample_video(
            media_id=media_id,
            project_id=resolved_project,
            scale=scale_label,
            out_path=out_path,
        )

    from gflow_cli.storage import is_cloud_path

    target_path = Path(str(target))
    file_bytes = (
        target_path.stat().st_size if target_path.exists() and not is_cloud_path(target) else 0
    )
    return {
        "status": "ok",
        "media_id": media_id,
        "project_id": resolved_project,
        "scale": scale_label,
        "path": str(target),
        "bytes": file_bytes,
    }


@server.tool(
    name="gflow_list_projects",
    description=(
        "List local catalog projects by default, or source=google for a native account page. "
        "Google pages use an opaque cursor and fixed size 21; optional bounded all_pages "
        "traversal and include_history with separate bounded history controls. "
        "Completeness remains unknown."
    ),
)
@_guarded
async def gflow_list_projects(
    profile: str = _DEFAULT_PROFILE,
    limit: int | None = None,
    offset: int = 0,
    source: str = "local",
    cursor: str | None = None,
    all_pages: StrictBool = False,
    max_pages: StrictInt | None = None,
    include_catalogs: StrictBool = False,
    max_projects: StrictInt | None = None,
    catalog_project_ids: list[str] | None = None,
    include_history: StrictBool = False,
    history_cursor: str | None = None,
    history_max_pages: StrictInt | None = None,
    history_max_media: StrictInt | None = None,
) -> dict[str, Any]:
    """List local SQLite rows or an explicitly selected native Google page.

    Args:
        profile: gflow-cli profile name to filter by.
        source: local catalog (default) or live google account snapshot.
        cursor: Opaque next_cursor from a Google page; at most 4096 characters.
        all_pages: Traverse Google pages with one browser lease; default false.
        max_pages: Optional cap 1–100 with all_pages; default 100.
        include_catalogs: Include typed media/workflow/character/saved-voice observations.
        max_projects: Optional cap 1–20 with include_catalogs; default 20.
        catalog_project_ids: Resume 1–20 explicit pending project UUIDs in supplied order;
            requires include_catalogs and excludes account cursor/traversal controls.
        include_history: Include bounded account history; default false.
        history_cursor: Opaque account-history continuation with include_history.
        history_max_pages: Optional history cap 1–50; default 50.
        history_max_media: Optional history media cap 1–1000; default 1000.
        limit: Local page size, default 50; omit for Google pages.
        offset: Number of rows to skip — pass the previous page's
            ``next_offset`` to fetch the next page (#498).

    Returns:
        Local: projects/count/offset/has_more/next_offset. Google: projects,
        next_cursor, returned_count, pages_read, pagination_exhausted, scope
        and complete=None. Optional catalogs contain known returned counts and
        pending discovered project IDs, separately from later-page continuation. Optional
        account_history has separate workflow/media counts, history continuation and
        traversal exhaustion; completeness remains unknown. Google snapshots
        neither update local catalog entries nor infer missing-project deletion.
    """
    try:
        validate_project_traversal(all_pages, max_pages)
        validate_project_catalogs(include_catalogs, max_projects)
        resume_ids = validate_project_catalog_resume(
            include_catalogs, catalog_project_ids, cursor, all_pages, max_pages
        )
        from gflow_cli.api.native_history import validate_project_history_options

        validate_project_history_options(
            include_history, history_cursor, history_max_pages, history_max_media
        )
    except ValueError as exc:
        return _bad_param("Invalid native catalog controls", str(exc))
    if source != "google" and (
        all_pages
        or max_pages is not None
        or include_catalogs
        or max_projects is not None
        or catalog_project_ids is not None
        or include_history
        or history_cursor is not None
        or history_max_pages is not None
        or history_max_media is not None
    ):
        return _bad_param("Invalid native catalog controls", "Traversal requires source=google")
    if source not in {"local", "google"}:
        return _bad_param("Invalid native catalog controls", "source must be local or google")
    if source == "google":
        if limit is not None or offset != 0:
            return _bad_param(
                "Invalid native catalog controls",
                "Google pages are fixed at 21; omit limit and offset",
            )
        if cursor is not None and (not cursor or len(cursor) > 4096):
            return _bad_param(
                "Invalid native catalog controls", "Google cursor must contain 1–4096 characters"
            )
        resume_options: dict[str, Any] = (
            {"catalog_project_ids": resume_ids} if resume_ids is not None else {}
        )
        resolved = _resolve_and_validate_profile(profile)
        if isinstance(resolved, dict):
            return resolved
        settings = get_settings()
        async with _profile_lock(resolved):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                if include_history:
                    snapshot = await client.list_native_projects(
                        cursor=cursor,
                        all_pages=all_pages,
                        max_pages=max_pages,
                        include_catalogs=include_catalogs,
                        max_projects=max_projects,
                        **resume_options,
                        include_history=True,
                        history_cursor=history_cursor,
                        history_max_pages=history_max_pages,
                        history_max_media=history_max_media,
                    )
                elif include_catalogs:
                    snapshot = await client.list_native_projects(
                        cursor=cursor,
                        all_pages=all_pages,
                        max_pages=max_pages,
                        include_catalogs=True,
                        max_projects=max_projects,
                        **resume_options,
                    )
                else:
                    snapshot = (
                        await client.list_native_projects(
                            cursor=cursor, all_pages=all_pages, max_pages=max_pages
                        )
                        if all_pages
                        else await client.list_native_projects(cursor=cursor)
                    )
        return {"status": "ok", **snapshot}
    if cursor is not None:
        return _bad_param("Invalid native catalog controls", "cursor requires source=google")
    limit = 50 if limit is None else limit
    log.info("mcp.tool.list_projects", profile=profile, limit=limit)

    settings = get_settings()
    db_path = settings.resolved_db_path()

    # No local funnel: @_guarded produces the ONE consistent error envelope.
    # An inner `except Exception` here used to swallow GFlowErrors (e.g.
    # DataStoreError) into a masked string, and gave this tool a second,
    # incompatible error shape (council review of #473).
    # Clamp before touching SQL: limit<=0 previously produced has_more=True
    # with an empty page and next_offset==offset (a documented-loop trap), and
    # negative limits reached SQLite as LIMIT -1 (unbounded read).
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    # Fetch one extra row to learn whether another page exists without a
    # separate COUNT query (#498) — the page itself is rows[:limit].
    fetched = list_projects(
        db_path=db_path,
        profile=profile if profile != "default" else None,
        limit=limit + 1,
        offset=offset,
    )
    rows = fetched[:limit]
    has_more = len(fetched) > limit
    return {
        "status": "ok",
        "projects": [local_project_payload(row) for row in rows],
        "count": len(rows),
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }


@server.tool(
    name="gflow_project_media",
    description="Read native project media; never syncs or deletes local catalog assets.",
)
@_guarded
async def gflow_project_media(
    project: str, source: str = "google", profile: str = _DEFAULT_PROFILE
) -> dict[str, Any]:
    """Read mixed native media; unknown kinds/completeness remain explicit.

    Args:
        project: Native project UUID.
        source: Only google is supported for this read-only snapshot.
        profile: Profile owning the selected project.
    """
    if source != "google":
        return _bad_param("Invalid native catalog controls", "project media source must be google")
    if not is_uuid(project):
        return _bad_param("Invalid native project", "Native project identifier must be a UUID")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            snapshot = await client.list_native_media(project)
    return {"status": "ok", **snapshot}


@server.tool(
    name="gflow_upload_video",
    description="Upload one regular MP4; explicit per-request rights, no generation or replay.",
)
@_guarded
async def gflow_upload_video(
    path: str, project: str, rights_confirmed: StrictBool = False, profile: str = _DEFAULT_PROFILE
) -> dict[str, Any]:
    """Upload an identified MP4 from a private snapshot.

    Args:
        path: Local regular MP4 path, identified not fully decoded.
        project: Native project UUID.
        rights_confirmed: Must be exactly true for this upload.
        profile: Owning saved profile.
    """
    from gflow_cli.api.native_media import upload_snapshot_context, validate_upload
    from gflow_cli.services.native_media import upload_private_snapshot

    selected = validate_upload(project, rights_confirmed)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    result: dict[str, Any] = {}
    async with _profile_lock(resolved):
        with upload_snapshot_context(
            Path(path), project=selected, rights_confirmed=rights_confirmed, outcome=result
        ) as private:
            result.update(await upload_private_snapshot(resolved, selected, private))
    return {"status": "ok", **result}


@server.tool(
    name="gflow_archive_media",
    description="Reversibly move complete owned media batches to trash; explicit confirmation.",
)
@_guarded
async def gflow_archive_media(
    media_ids: list[str],
    project: str,
    confirm_archive: StrictBool = False,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Archive complete native batches without automatic mutation replay.

    Args:
        media_ids: One to 100 distinct active owned media UUIDs, including every sibling.
        project: Native project UUID.
        confirm_archive: Must be exactly true; operation is reversible move to trash.
        profile: Owning saved profile.
    """
    from gflow_cli.api.native_media import validate_archive
    from gflow_cli.services.native_media import archive_media

    selected, identifiers = validate_archive(project, media_ids, confirm_archive)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    async with _profile_lock(resolved):
        result = await archive_media(resolved, selected, identifiers)
    return {"status": "ok", **result}


@server.tool(
    name="gflow_auth_status",
    description=(
        "Non-interactive, credit-free Flow session probe (#497). Call this "
        "BEFORE a generation tool to fail fast on expired auth — the queue is "
        "async, so an auth failure otherwise surfaces only later from the "
        "daemon. Never starts an interactive login flow; may boot a "
        "short-lived headless browser only if cookie decryption requires the "
        "Playwright fallback. May take up to ~45s on a slow network."
    ),
)
@_guarded
async def gflow_auth_status(profile: str = _DEFAULT_PROFILE) -> dict[str, Any]:
    """Probe the profile's Flow session without any interaction.

    Wraps :func:`gflow_cli.auth.verification.verify_flow_profile` — the same
    fail-closed probe behind ``gflow auth status``. Login/logout stay CLI-only
    (genuinely interactive); this tool only *reports*.

    Args:
        profile: gflow-cli profile name (``"default"`` auto-resolves like the CLI).

    Returns:
        ``{"status": "authenticated", "profile", "user_email"}`` on success;
        otherwise ``{"status": <outcome>, "profile", "error": {...problem
        details with remediation_hint...}}``.
    """
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    log.info("mcp.tool.auth_status", profile=resolved)
    status = await verification.verify_flow_profile(auth_mod.profile_dir(resolved), source="mcp")
    if status.authenticated:
        return {
            "status": "authenticated",
            "profile": resolved,
            "user_email": status.user_email,
        }
    if status.outcome is verification.FlowSessionOutcome.PROFILE_MARKER_MISSING:
        # #796: a local profile-state fault. Not retryable (the marker will not
        # reappear on its own) and not an expired session, so neither 503 nor 401
        # describes it — an agent that retries or re-logins here learns nothing.
        error = {
            "type": "https://gflow-cli.dev/errors/profile-marker-missing",
            "title": "Profile is missing its browser-strategy marker",
            "status": 409,
            "detail": status.detail,
            "message": status.detail,
            "retryable": False,
            "remediation_hint": (
                "This profile has no `.gflow_browser_strategy` marker, so its "
                "cookies cannot be read. Re-run `gflow auth login --browser "
                "chrome` for this profile to rewrite it."
            ),
        }
    elif status.outcome is verification.FlowSessionOutcome.VERIFICATION_ERROR:
        # A network/endpoint problem is not fixed by re-login — the
        # machine-readable discriminators must say so too (post-merge review:
        # labeling this 401/auth-expired sent type-dispatching agents into an
        # unnecessary interactive re-login on every network blip).
        error: dict[str, Any] = {
            "type": "https://gflow-cli.dev/errors/verification-error",
            "title": "Flow session verification failed",
            "status": 503,
            "detail": status.detail,
            "message": status.detail,
            "retryable": True,
            "remediation_hint": (
                "Could not verify the Flow session (network or endpoint "
                "problem). Check connectivity and retry; re-login is only "
                "needed if the session is actually dead."
            ),
        }
    else:
        from gflow_cli.errors import AuthExpiredError

        error = {
            **_gflow_error_dict(AuthExpiredError(status.detail)),
            # AuthExpiredError only carries an HTTP status when built from a
            # real response; a dead/missing session is semantically a 401.
            "status": 401,
            "remediation_hint": (
                f"Run 'gflow auth login --profile {resolved}' in your local "
                "terminal (interactive; not available through MCP)."
            ),
        }
    return {
        "status": status.outcome.value,
        "profile": resolved,
        "error": error,
    }


# gflow_list_characters was removed in #499: it was a stub that always
# answered {"status": "ok", "characters": []} — an agent reads that as "the
# user has no characters" and acts on the lie. Re-add only when it can
# return real Flow-side data (needs project_id + a browser session).


# ---------------------------------------------------------------------------
# Instructions — persistent Agent-Mode brief cards (CLI parity: `gflow instructions`)
# ---------------------------------------------------------------------------
#
# These are credits-free brief PATCHes, not queued generations, so they open a
# FlowApiClient session directly (like the CLI `_run_*` helpers) instead of
# going through FlowWorker. All mutations are read-modify-write against the
# LIVE server brief with card ids preserved — same contract cli_instructions
# pins. No token-bucket: only generations burn credits; the per-profile lock
# still serialises browser sessions.


def _card_dict(card: AgentInstruction) -> dict[str, Any]:
    """One card in the stable JSON shape shared with `gflow instructions --json`."""
    return {
        "id": card.id,
        "title": card.resolved_title(),
        "enabled": card.enabled,
        "text": card.text,
        "image_media_ids": list(card.image_media_ids),
        "character_ids": list(card.character_ids),
    }


def _ok_payload(project: str, **extra: Any) -> dict[str, Any]:
    """Standard success envelope for the instructions tools."""
    return {"status": "ok", "project_id": project, **extra}


def _error_payload(error: dict[str, Any]) -> dict[str, Any]:
    """Standard failure envelope (mirrors the generate tools' shape)."""
    return {"status": "error", "error": error}


def _format_mcp_error(exc: GFlowError) -> str:
    """Format a GFlowError for MCP tool error responses.

    Includes the error class name, detail (or title if detail is empty),
    and remediation hint if present:
    `[error_class] detail (Remediation: remediation_hint)`
    """
    error_class = type(exc).__name__
    main_msg = exc.detail if exc.detail else exc.title
    if exc.remediation_hint:
        return f"[{error_class}] {main_msg} (Remediation: {exc.remediation_hint})"
    return f"[{error_class}] {main_msg}"


def _gflow_error_dict(exc: GFlowError) -> dict[str, Any]:
    """Problem-details dict + the shared retryable flag (``errors.is_retryable``)
    so the MCP envelope's retry signal stays identical to CLI ``--json`` and the
    worker queue — never fork a private retryable list here (§6.5)."""
    return {
        **exc.to_problem_details(),
        "message": _format_mcp_error(exc),
        "retryable": is_retryable(exc),
    }


def _selector_error(title: str | None, card_id: str | None) -> dict[str, Any] | None:
    """Enforce exactly one of title / card_id (mirrors the CLI selector rule)."""
    if (title is None) == (card_id is None):
        return _bad_param("Invalid Card Selector", "Provide exactly one of 'title' or 'card_id'.")
    return None


async def _run_instructions_op(
    *,
    tool: str,
    profile: str,
    project: str,
    op: Callable[[FlowApiClient], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Shared plumbing for the instructions tools.

    Validates the project id, resolves the profile, serialises on the
    per-profile lock, opens a FlowApiClient session, and maps failures to the
    standard envelopes: ``ValueError`` (card selection / card invariants) →
    RFC 9457 bad-parameter, ``GFlowError`` → its problem details, anything
    else → 500.
    """
    if not project:
        return _bad_param(
            "Missing Project Id",
            "'project' is required — persistent "
            "instruction cards only exist on a real Flow project.",
        )
    if (proj_err := _validate_project(project)) is not None:
        return proj_err

    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved

    settings = get_settings()
    profile_dir = settings.profile_subdir(resolved)
    log.info("mcp.tool.instructions", tool=tool, project=project, profile=resolved)
    try:
        async with (
            _profile_lock(resolved),
            FlowApiClient(profile_dir=profile_dir, headless=settings.headless) as client,
        ):
            # ValueError is scoped to op() ONLY — brief.find (not-found /
            # ambiguous) and AgentInstruction invariants raise it with
            # user-facing messages built from the caller's own card data. A
            # ValueError from client session setup/teardown could embed
            # paths/URLs and must fall through to @_guarded's masked envelope
            # instead (council review of #473).
            try:
                return await op(client)
            except ValueError as exc:
                return _bad_param("Invalid Instructions Request", str(exc))
    except GFlowError as exc:
        log.error("mcp.tool.instructions_gflow_error", tool=tool, error=str(exc))
        return _error_payload(_gflow_error_dict(exc))
    except Exception as exc:
        log.exception("mcp.tool.instructions_unexpected_error", tool=tool, exc_info=exc)
        return _error_payload(_masked_unexpected_dict(exc))


@server.tool(
    name="gflow_instructions_list",
    description=(
        "List a Flow project's persistent Agent-Mode instruction cards "
        "(reads the live server brief). Credits-free."
    ),
)
@_guarded
async def gflow_instructions_list(
    project: str,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """List the instruction cards on the project's brief.

    Args:
        project: Flow project id (required — briefs are project-scoped).
        profile: gflow-cli profile name; 'default' auto-resolves like the CLI.

    Returns:
        Dict with 'status', 'project_id', 'enabled' (brief master switch) and
        'cards' (id/title/enabled/text/image_media_ids/character_ids each).
    """

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        brief = await client.get_agent_info(project)
        return _ok_payload(
            project,
            enabled=brief.enabled,
            cards=[_card_dict(c) for c in brief.cards],
        )

    return await _run_instructions_op(
        tool="gflow_instructions_list", profile=profile, project=project, op=_op
    )


@server.tool(
    name="gflow_instructions_add",
    description=(
        "Add a persistent instruction card to a Flow project's Agent-Mode brief "
        "(credits-free). Each ref is classified automatically: local image path "
        "→ uploaded as an image reference; asset UUID → image reference; "
        "anything else → character id/name."
    ),
)
@_guarded
async def gflow_instructions_add(
    project: str,
    title: str,
    text: str,
    refs: list[str] | None = None,
    enabled: bool = True,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Add an instruction card to the project's brief.

    Args:
        project: Flow project id (required).
        title: Human-readable card label (used for later selection by title).
        text: Guideline text the agent folds into every generation.
        refs: Optional references — local image paths, asset UUIDs, or
            character ids/names (classified automatically, like CLI --ref).
        enabled: Create the card enabled (default) or disabled.
        profile: gflow-cli profile name.

    Returns:
        Dict with 'status', 'project_id', and the created 'card'.
    """

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        brief = await client.get_agent_info(project)
        image_ids, char_ids = await classify_refs(client, project, tuple(refs or ()))
        card = AgentInstruction(
            text=text,
            enabled=enabled,
            image_media_ids=tuple(image_ids),
            character_ids=tuple(char_ids),
            title=title,
        )
        # Send the FULL card set (existing + new): patch_agent_info REPLACES the
        # brief's cards, and existing cards keep their ids via read-modify-write.
        await client.patch_agent_info(project, enabled=True, cards=(*brief.cards, card))
        return _ok_payload(project, card=_card_dict(card))

    return await _run_instructions_op(
        tool="gflow_instructions_add", profile=profile, project=project, op=_op
    )


@server.tool(
    name="gflow_instructions_set_enabled",
    description=(
        "Enable or disable one instruction card on a Flow project's brief, "
        "selected by title or card id (exactly one). Credits-free."
    ),
)
@_guarded
async def gflow_instructions_set_enabled(
    project: str,
    enabled: bool,
    title: str | None = None,
    card_id: str | None = None,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Flip one card's enabled flag (covers CLI `instructions enable`/`disable`).

    Args:
        project: Flow project id (required).
        enabled: True to enable the card, False to disable it.
        title: Select the card by title (case-insensitive, must be unambiguous).
        card_id: Select the card by its stable server id.
        profile: gflow-cli profile name.

    Returns:
        Dict with 'status', 'project_id', and the updated 'card'.
    """
    if (sel_err := _selector_error(title, card_id)) is not None:
        return sel_err

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        brief = await client.get_agent_info(project)
        card = brief.find(title=title) if card_id is None else brief.find(card_id=card_id)
        # Replace the target in place (preserving its id) and PATCH the FULL set.
        # cast: replace() loses the concrete type for Sonar S5655 (see sonar-dataclasses-replace).
        updated = cast("AgentInstruction", replace(card, enabled=enabled))  # pyright: ignore[reportUnnecessaryCast]
        new_cards = tuple(updated if c is card else c for c in brief.cards)
        await client.patch_agent_info(project, enabled=True, cards=new_cards)
        return _ok_payload(project, card=_card_dict(updated))

    return await _run_instructions_op(
        tool="gflow_instructions_set_enabled", profile=profile, project=project, op=_op
    )


@server.tool(
    name="gflow_instructions_rm",
    description=(
        "Remove one instruction card from a Flow project's brief, selected by "
        "title or card id (exactly one). Credits-free."
    ),
)
@_guarded
async def gflow_instructions_rm(
    project: str,
    title: str | None = None,
    card_id: str | None = None,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Remove the selected card from the project's brief.

    Args:
        project: Flow project id (required).
        title: Select the card by title (case-insensitive, must be unambiguous).
        card_id: Select the card by its stable server id.
        profile: gflow-cli profile name.

    Returns:
        Dict with 'status', 'project_id', and the removed 'card'.
    """
    if (sel_err := _selector_error(title, card_id)) is not None:
        return sel_err

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        brief = await client.get_agent_info(project)
        card = brief.find(title=title) if card_id is None else brief.find(card_id=card_id)
        # Drop the target; send the remaining set (possibly empty -> clears it).
        new_cards = tuple(c for c in brief.cards if c is not card)
        await client.patch_agent_info(project, enabled=True, cards=new_cards)
        return _ok_payload(project, card=_card_dict(card))

    return await _run_instructions_op(
        tool="gflow_instructions_rm", profile=profile, project=project, op=_op
    )


@server.tool(
    name="gflow_instructions_toggle_mode",
    description=(
        "Turn a Flow project's brief master switch on or off. When off, NO "
        "cards apply even if individually enabled. Cards are left untouched. "
        "Credits-free."
    ),
)
@_guarded
async def gflow_instructions_toggle_mode(
    project: str,
    enabled: bool,
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Toggle the brief-level master switch (CLI `instructions toggle-mode`).

    Args:
        project: Flow project id (required).
        enabled: True for --on, False for --off.
        profile: gflow-cli profile name.

    Returns:
        Dict with 'status', 'project_id', and 'agent_mode_enabled'.
    """

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        # Master switch only — cards are left untouched (no cards= mask sent).
        await client.patch_agent_info(project, enabled=enabled)
        return _ok_payload(project, agent_mode_enabled=enabled)

    return await _run_instructions_op(
        tool="gflow_instructions_toggle_mode", profile=profile, project=project, op=_op
    )


@server.tool(
    name="gflow_instructions_apply",
    description=(
        "Declaratively FULL-SYNC a Flow project's brief: REPLACES all existing "
        "instruction cards with the given set (destructive — cards not listed "
        "are removed). Each card is {'title', 'text', 'ref': [...], 'enabled'}. "
        "Credits-free."
    ),
)
@_guarded
async def gflow_instructions_apply(
    project: str,
    cards: list[dict[str, Any]],
    profile: str = _DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Full-sync the project's brief from a declarative card list.

    Args:
        project: Flow project id (required).
        cards: Declarative card entries; each is a dict with 'title' (str),
            'text' (str), optional 'ref' (list of image paths / asset UUIDs /
            character ids) and optional 'enabled' (bool, default True).
            This is the same entry shape as the CLI `instructions apply` file.
        profile: gflow-cli profile name.

    Returns:
        Dict with 'status', 'project_id', and the applied 'cards'.
    """

    async def _op(client: FlowApiClient) -> dict[str, Any]:
        built: list[AgentInstruction] = []
        for entry in cards:
            raw_refs = entry.get("ref", [])
            if not isinstance(raw_refs, list):
                msg = "each card's 'ref' must be a list of strings."
                raise ValueError(msg)
            refs = tuple(str(r) for r in cast("list[Any]", raw_refs))
            image_ids, char_ids = await classify_refs(client, project, refs)
            built.append(
                AgentInstruction(
                    text=str(entry.get("text", "")),
                    enabled=bool(entry.get("enabled", True)),
                    image_media_ids=tuple(image_ids),
                    character_ids=tuple(char_ids),
                    title=str(entry.get("title", "")),
                )
            )
        # Full replace: the given list is the declarative source of truth.
        await client.patch_agent_info(project, enabled=True, cards=tuple(built))
        return _ok_payload(project, cards=[_card_dict(c) for c in built])

    return await _run_instructions_op(
        tool="gflow_instructions_apply", profile=profile, project=project, op=_op
    )


# Re-export Path so tests that import it directly still work
__all__ = [
    "gflow_generate_image",
    "gflow_generate_video",
    "gflow_list_tools",
    "gflow_list_projects",
    "gflow_project_media",
    "gflow_upload_video",
    "gflow_archive_media",
    "gflow_download_media",
    "gflow_upscale_image",
    "gflow_upscale_video",
    "gflow_auth_status",
    "gflow_instructions_list",
    "gflow_instructions_add",
    "gflow_instructions_set_enabled",
    "gflow_instructions_rm",
    "gflow_instructions_toggle_mode",
    "gflow_instructions_apply",
    "_TokenBucket",
    "_adapt_tools",
    "_format_mcp_error",
    "_gflow_error_dict",
    "_run_generation_task",
]


async def _saved_voice_tool(
    operation: str, project: str, profile: str, **kwargs: Any
) -> dict[str, Any]:
    from gflow_cli.api.native_voices import validate_create
    from gflow_cli.api.transports.native_voices import validate_identifier
    from gflow_cli.services.native_voices import saved_voice_operation

    try:
        validate_identifier(project)
        if operation in {"get", "delete"}:
            validate_identifier(kwargs.get("voice_id"))
        if operation == "create":
            validate_create(
                project,
                kwargs["display_name"],
                kwargs["preset_voice"],
                kwargs["dialog"],
                kwargs["performance"],
            )
        if operation == "delete" and kwargs.get("confirm_delete") is not True:
            raise ConfigurationError(detail="Saved voice deletion requires confirm_delete=true")
    except ValueError as exc:
        return _bad_param("Invalid saved voice request", str(exc))
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    if operation == "create" and not await _rate_limiter.acquire():
        return _rate_limited_envelope()
    async with _profile_lock(resolved):
        result = await saved_voice_operation(
            profile=resolved, operation=cast(Any, operation), project_id=project, **kwargs
        )
    return {"status": "ok", **result}


@server.tool(
    name="gflow_list_saved_voices",
    description="List saved TTS audio voices in an owned native Google Flow project.",
)
@_guarded
async def gflow_list_saved_voices(project: str, profile: str = "default") -> dict[str, Any]:
    return await _saved_voice_tool("list", project, profile)


@server.tool(
    name="gflow_get_saved_voice",
    description="Read one saved TTS voice by owned media UUID. No generation.",
)
@_guarded
async def gflow_get_saved_voice(
    project: str, voice_id: str, profile: str = "default"
) -> dict[str, Any]:
    return await _saved_voice_tool("get", project, profile, voice_id=voice_id)


@server.tool(
    name="gflow_create_saved_voice",
    description="Generate a TTS preview from a system preset and save a named voice. "
    "Consumes credits; dialog/performance each 1..120. Optional single-use captcha_token.",
)
@_guarded
async def gflow_create_saved_voice(
    project: str,
    display_name: str,
    preset_voice: str,
    dialog: str,
    performance: str,
    profile: str = "default",
    captcha_token: str | None = None,
) -> dict[str, Any]:
    with native_captcha_or_none(captcha_token, project_id=project, action="AUDIO_GENERATION"):
        return await _saved_voice_tool(
            "create",
            project,
            profile,
            display_name=display_name,
            preset_voice=preset_voice,
            dialog=dialog,
            performance=performance,
        )


@server.tool(
    name="gflow_delete_saved_voice",
    description="Permanently delete an owned saved TTS voice; requires confirm_delete=true.",
)
@_guarded
async def gflow_delete_saved_voice(
    project: str, voice_id: str, confirm_delete: StrictBool = False, profile: str = "default"
) -> dict[str, Any]:
    return await _saved_voice_tool(
        "delete", project, profile, voice_id=voice_id, confirm_delete=confirm_delete
    )


def _native_video_checkpoint(target: Path, operation: str) -> Callable[[Any], Awaitable[None]]:
    path = target / f"mcp-{operation}-started-{uuid.uuid4().hex}.json"

    async def checkpoint(started: Any) -> None:
        record = {
            "project_id": started.project_id,
            "media_ids": list(started.media_ids),
            "workflow_ids": list(started.workflow_ids),
        }
        source = getattr(started, "source_media_id", None)
        if source is not None:
            record["source_media_id"] = source
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            json.dump(record, stream)

    return checkpoint


async def _download_native_video_results(
    client: FlowApiClient, records: Any, target: Path, unknown: GFlowError
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        for record in records:
            if not record.video_url:
                raise unknown
            path = target / f"{record.media_id}.mp4"
            await client.download(record.video_url, path)
            results.append(
                {
                    "media_id": record.media_id,
                    "workflow_id": record.workflow_id,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                }
            )
    except asyncio.CancelledError:
        # The pre-submit journal retains recovery IDs; cancellation stays cancellation.
        raise
    except Exception:
        raise unknown from None
    return results


@server.tool(
    name="gflow_extend_native_video",
    description="Generate standalone continuation clips from an owned native video. "
    "Optional native model_key; otherwise selects an available low-cost model. "
    "Count1..4; downloads MP4 outputs. "
    "Consumes video generation credits.",
)
@_guarded
async def gflow_extend_native_video(
    project: str,
    media_id: str,
    prompt: str,
    model_key: str | None = None,
    count: int = 1,
    aspect: str | None = None,
    trim_start_frame: int | None = None,
    trim_end_frame: int | None = None,
    out_dir: str | None = None,
    profile: str = "default",
    captcha_token: str | None = None,
) -> dict[str, Any]:
    with native_captcha_or_none(captcha_token, project_id=project, action="VIDEO_GENERATION"):
        from gflow_cli.api.native_extension import (
            NativeExtensionUnknownError,
            extension_args,
            new_extension_started,
        )

        if not is_uuid(project) or not is_uuid(media_id):
            return _bad_param("Invalid video extension identifiers", "Project/media must be UUIDs")
        if type(count) is not int or not 1 <= count <= 4:
            return _bad_param("Invalid video extension count", "count must be1..4")
        extension_args(
            new_extension_started(project, media_id, count),
            prompt=prompt,
            model_key=model_key or "validation-native-model",
            aspect=aspect or "16:9",
            token="validation-only",
            trim_start_frame=trim_start_frame,
            trim_end_frame=trim_end_frame,
        )
        resolved = _resolve_and_validate_profile(profile)
        if isinstance(resolved, dict):
            return resolved
        if not await _rate_limiter.acquire():
            return _rate_limited_envelope()
        settings = get_settings()
        target = Path(out_dir) if out_dir else settings.output_dir
        target.mkdir(parents=True, exist_ok=True)
        async with _profile_lock(resolved):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                started = await client.extend_native_video(
                    project_id=project,
                    media_id=media_id,
                    prompt=prompt,
                    model_key=model_key,
                    count=count,
                    aspect=aspect,
                    trim_start_frame=trim_start_frame,
                    trim_end_frame=trim_end_frame,
                    on_started=_native_video_checkpoint(target, "extend"),
                )
                records = await client.wait_native_extension(started)
                results = await _download_native_video_results(
                    client, records, target, NativeExtensionUnknownError(started)
                )
        return {
            "status": "ok",
            "project_id": project,
            "source_media_id": media_id,
            "results": results,
        }


@server.tool(
    name="gflow_list_extension_models",
    description="Read available native video extension model keys and per-output credit costs.",
)
@_guarded
async def gflow_list_extension_models(project: str, profile: str = "default") -> dict[str, Any]:
    if not is_uuid(project):
        return _bad_param("Invalid project", "project must be a UUID")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            models = await client.list_native_extension_models(project)
    return {"status": "ok", "project_id": project, "models": models}


@server.tool(
    name="gflow_delete_native_media",
    description="Permanently delete only selected owned image/video/audio media IDs. "
    "Preserves sibling media; requires confirm_delete=true. "
    "Confirmed deletions can be repeated with fresh account/project proof; "
    "unknown missing IDs refuse.",
)
@_guarded
async def gflow_delete_native_media(
    project: str, media_ids: list[str], confirm_delete: StrictBool = False, profile: str = "default"
) -> dict[str, Any]:
    from gflow_cli.api.transports.native_media_delete import validate_delete

    validate_delete(project, media_ids, confirm_delete)
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            result = await client.delete_native_media(
                project_id=project, media_ids=media_ids, confirm_delete=confirm_delete
            )
    return {"status": "ok", **result}


@server.tool(
    name="gflow_edit_native_video",
    description="Edit an owned video with Omni Flash. Virtual24fps trim window0..240; "
    "up to5 owned images,3 audio UUID/preset refs and owned characters with native limits. "
    "Explicit native "
    "model_key required; omitted end uses measured source duration capped240 frames. "
    "Consumes video credits; optional confidential single-use captcha_token.",
)
@_guarded
async def gflow_edit_native_video(
    project: str,
    media_id: str,
    prompt: str,
    model_key: str,
    end_frame: int | None = None,
    start_frame: int = 0,
    image_ref: list[str] | None = None,
    audio_ref: list[str] | None = None,
    character_ref: list[str] | None = None,
    out_dir: str | None = None,
    profile: str = "default",
    captcha_token: str | None = None,
) -> dict[str, Any]:
    with native_captcha_or_none(captcha_token, project_id=project, action="VIDEO_GENERATION"):
        from gflow_cli.api.native_extension import new_extension_started
        from gflow_cli.api.native_video_edit import NativeVideoEditUnknownError, video_edit_args

        if not is_uuid(project) or not is_uuid(media_id):
            return _bad_param("Invalid video edit identifiers", "Project/media must be UUIDs")
        images, audio = tuple(image_ref or []), tuple(audio_ref or [])
        characters = tuple(character_ref or [])
        video_edit_args(
            new_extension_started(project, media_id, 1),
            prompt=prompt,
            model_key=model_key,
            aspect="16:9",
            token="validation-only",
            start_frame=start_frame,
            end_frame=end_frame if end_frame is not None else 240,
            image_ids=images,
            audio_ids=audio,
            character_ids=characters,
        )
        resolved = _resolve_and_validate_profile(profile)
        if isinstance(resolved, dict):
            return resolved
        if not await _rate_limiter.acquire():
            return _rate_limited_envelope()
        settings = get_settings()
        target = Path(out_dir) if out_dir else settings.output_dir
        target.mkdir(parents=True, exist_ok=True)
        async with _profile_lock(resolved):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                started = await client.edit_native_video(
                    project_id=project,
                    media_id=media_id,
                    prompt=prompt,
                    model_key=model_key,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    image_ids=images,
                    audio_ids=audio,
                    character_ids=characters,
                    on_started=_native_video_checkpoint(target, "edit"),
                )
                records = await client.wait_native_video_edit(started)
                results = await _download_native_video_results(
                    client, records, target, NativeVideoEditUnknownError(started)
                )
        return {
            "status": "ok",
            "project_id": project,
            "source_media_id": media_id,
            "results": results,
            "startFrameIndex": started.start_frame,
            "endFrameIndex": started.end_frame,
            "sourceDurationSeconds": started.source_duration_seconds,
        }


@server.tool(
    name="gflow_list_edit_models",
    description="List tier-available native Omni video edit keys and per-output credit costs.",
)
@_guarded
async def gflow_list_edit_models(project: str, profile: str = "default") -> dict[str, Any]:
    if not is_uuid(project):
        return _bad_param("Invalid project", "project must be a UUID")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            models = await client.list_native_video_edit_models(project)
    return {"status": "ok", "project_id": project, "models": models}


@server.tool(
    name="gflow_generate_native_reference_video",
    description="Generate Omni Flash with owned image/audio/character or system-preset refs; "
    "the chosen account model imposes its own limits. Optional native model_key, "
    "duration/resolution; downloads MP4 outputs. Consumes video credits; "
    "optional confidential single-use captcha_token.",
)
@_guarded
async def gflow_generate_native_reference_video(
    project: str,
    prompt: str,
    image_ref: list[str] | None = None,
    audio_ref: list[str] | None = None,
    character_ref: list[str] | None = None,
    model_key: str | None = None,
    count: int = 1,
    aspect: str = "16:9",
    duration: int | None = None,
    resolution: str = "720p",
    out_dir: str | None = None,
    profile: str = "default",
    captcha_token: str | None = None,
) -> dict[str, Any]:
    with native_captcha_or_none(captcha_token, project_id=project, action="VIDEO_GENERATION"):
        from gflow_cli.api.native_reference_video import new_reference_started, reference_args
        from gflow_cli.errors import NativeVideoGenerationUnknownError

        if not is_uuid(project):
            return _bad_param("Invalid project", "project must be a UUID")
        images, audio = tuple(image_ref or []), tuple(audio_ref or [])
        characters = tuple(character_ref or [])
        reference_args(
            new_reference_started(project, count),
            prompt=prompt,
            image_ids=images,
            audio_ids=audio,
            character_ids=characters,
            model_key=model_key or "discover-native-model",
            aspect=aspect,
            resolution=resolution,
            token="validation-only",
        )
        if duration is not None and (type(duration) is not int or not 1 <= duration <= 10):
            return _bad_param("Invalid duration", "duration must match an available native model")
        resolved = _resolve_and_validate_profile(profile)
        if isinstance(resolved, dict):
            return resolved
        if not await _rate_limiter.acquire():
            return _rate_limited_envelope()
        settings = get_settings()
        target = Path(out_dir) if out_dir else settings.output_dir
        target.mkdir(parents=True, exist_ok=True)
        async with _profile_lock(resolved):
            async with FlowApiClient(
                profile_dir=settings.profile_subdir(resolved), headless=settings.headless
            ) as client:
                started = await client.generate_native_reference_video(
                    project_id=project,
                    prompt=prompt,
                    reference_image_ids=images,
                    reference_audio_ids=audio,
                    reference_character_ids=characters,
                    model_key=model_key,
                    count=count,
                    aspect=aspect,
                    duration=duration,
                    resolution=resolution,
                    on_started=_native_video_checkpoint(target, "reference"),
                )
                records = await client.wait_native_reference_video(started)
                results = await _download_native_video_results(
                    client,
                    records,
                    target,
                    NativeVideoGenerationUnknownError(
                        project_id=started.project_id,
                        media_ids=started.media_ids,
                        workflow_ids=started.workflow_ids,
                        phase="video_poll",
                    ),
                )
        return {"status": "ok", "project_id": project, "results": results}


@server.tool(
    name="gflow_list_reference_video_models",
    description="List native reference-video model keys and costs; with_audio selects "
    "models capable of audio ingredients.",
)
@_guarded
async def gflow_list_reference_video_models(
    project: str, with_audio: StrictBool = False, profile: str = "default"
) -> dict[str, Any]:
    if not is_uuid(project):
        return _bad_param("Invalid project", "project must be a UUID")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            models = await client.list_native_reference_video_models(project, with_audio=with_audio)
    return {"status": "ok", "project_id": project, "models": models}


@server.tool(
    name="gflow_get_native_asset",
    description="Read owned native image/video/audio and confidential fresh URL; synchronous.",
)
@_guarded
async def gflow_get_native_asset(
    project: str, media_id: str, profile: str = _DEFAULT_PROFILE
) -> dict[str, Any]:
    """Read selected-project native image/video/audio; URL is ephemeral and confidential.

    Args:
        project: Native project UUID.
        media_id: Native media UUID; not a local artifact, character entity or voice workflow.
        profile: Owning saved profile. No account scanning.
    """
    if not is_uuid(project) or not is_uuid(media_id):
        return _bad_param("Invalid native asset", "Project and media identifiers must be UUIDs")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    from gflow_cli.services.native_assets import read_asset

    async with _profile_lock(resolved):
        return {"status": "ok", **await read_asset(resolved, project, media_id)}


@server.tool(
    name="gflow_download_native_asset",
    description="Download verified native image/video without generation or upscale.",
)
@_guarded
async def gflow_download_native_asset(
    project: str, media_id: str, output_dir: str, profile: str = _DEFAULT_PROFILE
) -> dict[str, Any]:
    """Download fresh owned native media; video content validation requires ffprobe.

    Args:
        project: Native project UUID.
        media_id: Native image/video UUID.
        output_dir: Local output directory; existing files are never overwritten.
        profile: Owning saved profile. No account scanning.
    """
    if not is_uuid(project) or not is_uuid(media_id):
        return _bad_param("Invalid native asset", "Project and media identifiers must be UUIDs")
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    from gflow_cli.services.native_assets import read_asset

    async with _profile_lock(resolved):
        return {"status": "ok", **await read_asset(resolved, project, media_id, Path(output_dir))}


@server.tool(
    name="gflow_upscale_native_video",
    description=(
        "Generate a native promoted video at720p,1080p or4k using available models. "
        "May spend credits; distinct from export. Optional confidential captcha_token."
    ),
)
@_guarded
async def gflow_upscale_native_video(
    project: str,
    media_id: str,
    resolution: str = "1080p",
    model_key: str | None = None,
    profile: str = "default",
    out_dir: str | None = None,
    captcha_token: str | None = None,
) -> dict[str, Any]:
    from gflow_cli.api.native_captcha import native_captcha_or_none
    from gflow_cli.selfhost.video_promotion_worker import run_promotion

    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    target = Path(out_dir) if out_dir else get_settings().output_dir / "promotions"
    with native_captcha_or_none(captcha_token, project_id=project, action="VIDEO_GENERATION"):
        async with _profile_lock(resolved):
            result = await run_promotion(
                resolved,
                project,
                {"mediaGenerationId": media_id, "resolution": resolution, "modelKey": model_key},
                target,
            )
    return {"status": "ok", **result}


@server.tool(
    name="gflow_list_video_upscale_models",
    description=("Read account-available video promotion models and costs for720p,1080p or4k."),
)
@_guarded
async def gflow_list_video_upscale_models(
    project: str, resolution: str = "1080p", profile: str = "default"
) -> dict[str, Any]:
    from gflow_cli.api.native_video_upscale import list_native_promotion_models

    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            models = await list_native_promotion_models(client, project, resolution=resolution)
    return {
        "status": "ok",
        "project_id": project,
        "target_resolution": resolution,
        "models": models,
    }


@server.tool(
    name="gflow_list_image_reference_models",
    description=(
        "Read fresh image reference budgets: advertised, transport and effective limits. "
        "Metadata does not prove retained references or rendered use."
    ),
)
@_guarded
async def gflow_list_image_reference_models(
    project: str, profile: str = "default"
) -> dict[str, Any]:
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            models = await client.list_native_image_reference_models(project)
    return {"status": "ok", "project_id": project, "models": models}


@server.tool(
    name="gflow_sync_native_inventory",
    description=(
        "Resume bounded native project discovery/catalogs and account history. "
        "Private metadata/checkpoints persist across calls; completeness stays unknown. "
        "Read-only direct execution; no generation queue."
    ),
)
@_guarded
async def gflow_sync_native_inventory(
    profile: str = "default",
    max_steps: StrictInt = 10,
    max_seconds: StrictInt = 180,
    restart: StrictBool = False,
) -> dict[str, Any]:
    from gflow_cli.profile_store import read_account_file
    from gflow_cli.services.inventory_sync import sync_native_inventory, validate_sync_options

    try:
        validate_sync_options(max_steps, max_seconds, restart)
    except ValueError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    account = read_account_file(settings.profile_subdir(resolved))
    if account is None:
        raise ConfigurationError(
            detail="Native inventory sync requires a recorded account identity"
        )
    async with _profile_lock(resolved):
        async with FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client:
            try:
                result = await sync_native_inventory(
                    client,
                    settings.home / "native_inventory",
                    profile=resolved,
                    account=account,
                    max_steps=max_steps,
                    max_seconds=max_seconds,
                    restart=restart,
                )
            except ValueError as exc:
                raise ConfigurationError(detail=str(exc)) from None
    return {"status": "ok", **result}


@server.tool(
    name="gflow_list_account_resources",
    description="Read observed account characters or saved-user voices across bounded native "
    "project catalogs. Explicit read extension; no generation/deletion or completeness claim.",
)
@_guarded
async def gflow_list_account_resources(
    kind: Literal["character", "voice"],
    profile: str = "default",
    cursor: str | None = None,
    max_projects: StrictInt = 10,
    max_pages: StrictInt = 1,
    max_seconds: StrictInt = 180,
) -> dict[str, Any]:
    from gflow_cli.services.account_resources import validate_account_resource_options

    try:
        validate_account_resource_options(kind, cursor, max_projects, max_pages, max_seconds)
    except ValueError as exc:
        raise ConfigurationError(detail=str(exc)) from None
    resolved = _resolve_and_validate_profile(profile)
    if isinstance(resolved, dict):
        return resolved
    settings = get_settings()
    async with (
        _profile_lock(resolved),
        FlowApiClient(
            profile_dir=settings.profile_subdir(resolved), headless=settings.headless
        ) as client,
    ):
        result = await client.list_account_resources(
            kind=kind,
            cursor=cursor,
            max_projects=max_projects,
            max_pages=max_pages,
            max_seconds=max_seconds,
        )
    return {"status": "ok", **result}
