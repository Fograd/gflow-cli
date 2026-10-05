"""A single daemon owns a durable queue; each configured profile has one worker."""

from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import hmac
import json
import math
import re
import shutil
import sqlite3
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gflow_cli.api.native_catalogs import (
    validate_project_catalog_resume,
    validate_project_catalogs,
    validate_project_traversal,
)
from gflow_cli.selfhost.config import (
    MAX_ASSET,
    MODEL_ALIASES,
    VIDEO_ALIASES,
    Settings,
    validate_callback,
)
from gflow_cli.selfhost.form_payload import FORM_REQUEST_BODY, parse_payload
from gflow_cli.selfhost.native_aliases import NativeAlias, NativeAliasStore, alias_spec
from gflow_cli.selfhost.native_observations import NativeObservationStore
from gflow_cli.selfhost.native_resource_aliases import (
    NativeResourceAlias,
    NativeResourceAliasStore,
    resource_alias_spec,
)
from gflow_cli.selfhost.quota_http import NoEligibleAccountHTTPError
from gflow_cli.selfhost.runtime import (
    contained_file,
    deliver_callbacks,
    parse_json_output,
    subprocess_run,
    worker,
)
from gflow_cli.selfhost.store import Store


class BodyLimitMiddleware:
    """Bound the receive stream before FastAPI buffers and parses JSON."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        size = 0
        path = scope.get("path", "")
        upload = scope.get("method") == "POST" and (
            path == "/v1/google-flow/assets" or path.startswith("/v1/google-flow/assets/")
        )
        limit = (
            MAX_ASSET
            if upload
            else 2 * 1024 * 1024
            if scope.get("method") == "POST" and path == "/v1/google-flow/accounts"
            else 65536
        )

        async def limited_receive() -> Message:
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise HTTPException(413, "Request body exceeds the operation limit")
            return message

        await self.app(scope, limited_receive, send)


def create_app(cfg: Settings, *, start_workers: bool = True) -> FastAPI:
    cfg.__post_init__()
    if not cfg.token:
        raise ValueError("Bearer token must be configured")
    store = Store(cfg.root)
    aliases = NativeAliasStore(cfg.root, resolve_scope=store.resolve_profile_scope)
    observations = NativeObservationStore(cfg.root)
    resource_aliases = NativeResourceAliasStore(cfg.root, resolve_scope=store.resolve_profile_scope)
    store.account_seed(cfg.accounts)
    cfg.accounts = {
        row["profile"]: {"email": row["email"], "project": row["project"]}
        for row in store.accounts()
        if row["enabled"] == 1
    }
    worker_tasks: dict[str, asyncio.Task[None]] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        tasks: list[asyncio.Task[None]] = []
        lock = None
        if start_workers:
            lock = (cfg.root / "daemon.lock").open("a")
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock.close()
                raise RuntimeError("Another self-host daemon already owns this queue") from None
            store.recover()
            # Disable/rebinding drops only queued scheduler reads before any worker can claim them.
            store.cancel_idle_health(cfg.idle_session_interval, cfg.accounts)
            worker_tasks.update(
                {
                    profile: asyncio.create_task(worker(cfg, store, profile))
                    for profile in cfg.accounts
                }
            )
            tasks.append(asyncio.create_task(deliver_callbacks(cfg, store)))
            if cfg.idle_session_interval:
                from gflow_cli.selfhost.idle_session import maintain_idle_sessions

                tasks.append(asyncio.create_task(maintain_idle_sessions(cfg, store)))
        try:
            yield
        finally:
            tasks.extend(worker_tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if lock:
                lock.close()

    async def authorised(
        request: Request,
        _credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
        ],
    ) -> None:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {cfg.token}".encode()):
            raise HTTPException(
                401, "Bearer authentication required", headers={"WWW-Authenticate": "Bearer"}
            )
        if request.query_params:
            path = request.url.path
            allowed: set[str] = set()
            if request.method == "GET":
                if path == "/v1/google-flow/accounts/captcha-stats":
                    allowed = {"date", "limit", "provider", "anonymized"}
                elif path == "/v1/google-flow/images/upscale/capabilities":
                    allowed = {"email", "projectId", "mediaGenerationId"}
                elif path == "/v1/google-flow/videos/upscale/models":
                    allowed = {"email", "projectId", "resolution"}
                elif path == "/v1/google-flow/videos/reference/models":
                    allowed = {"email", "projectId", "withAudio"}
                elif path in {
                    "/v1/google-flow/videos/extend/models",
                    "/v1/google-flow/videos/edit/models",
                    "/v1/google-flow/images/reference/models",
                }:
                    allowed = {"email", "projectId"}
                elif path == "/v1/google-flow/voices" or path.startswith("/v1/google-flow/voices/"):
                    allowed = {"email", "source", "catalog", "projectId"}
                elif path == "/v1/google-flow/characters" or path.startswith(
                    "/v1/google-flow/characters/"
                ):
                    allowed = {"email", "source", "projectId"}
                elif path == "/v1/google-flow/jobs":
                    allowed = {"email", "status", "kind", "limit", "cursor", "options", "source"}
                elif path.startswith("/v1/google-flow/assets/media/"):
                    allowed = {"projectId", "limit", "cursor", "source"}
                elif path.startswith("/v1/google-flow/assets/resources/"):
                    allowed = {"kind", "cursor", "maxProjects", "maxPages", "maxSeconds"}
                elif path.startswith("/v1/google-flow/assets/projects/"):
                    allowed = {
                        "limit",
                        "cursor",
                        "source",
                        "allPages",
                        "maxPages",
                        "includeCatalogs",
                        "catalogProjectIds",
                        "maxProjects",
                        "includeHistory",
                        "historyCursor",
                        "historyMaxPages",
                        "historyMaxMedia",
                    }
                elif path.startswith("/v1/google-flow/assets/") and not path.endswith("/download"):
                    allowed = {"raw", "source", "email", "projectId"}
            if request.method == "DELETE" and path.startswith("/v1/google-flow/characters/"):
                allowed = {"email", "projectId"}
            if request.method == "DELETE" and path.startswith("/v1/google-flow/voices/"):
                allowed = {"email", "projectId", "source", "async", "replyRef", "replyUrl"}
            if set(request.query_params) - allowed or len(
                request.query_params.multi_items()
            ) != len(request.query_params):
                raise HTTPException(
                    400 if path == "/v1/google-flow/accounts/captcha-stats" else 501,
                    {"code": "feature_not_implemented", "feature": "query parameters"},
                )

    app = FastAPI(
        title="Self-hosted Google Flow",
        lifespan=lifespan,
        dependencies=[Depends(authorised)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    app.state.aliases = aliases
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(NoEligibleAccountHTTPError)
    async def automatic_account_refused(
        request: Request, exc: NoEligibleAccountHTTPError
    ) -> JSONResponse:
        return JSONResponse(
            exc.payload, status_code=429, headers={"Retry-After": str(exc.retry_after)}
        )

    prefix = "/v1/google-flow"
    from gflow_cli.selfhost.captcha_routes import mount

    mount(app, cfg.root)

    def feature_missing(feature: str) -> None:
        raise HTTPException(
            501,
            {"code": "feature_not_implemented", "feature": feature, "status": "not_implemented"},
        )

    def pick_account(
        email: str | None,
        refs: list[str],
        *,
        allow_native: bool = False,
        operation: str | None = None,
        model_key: str | None = None,
    ) -> str:
        if not cfg.accounts:
            raise HTTPException(503, "No verified accounts configured")
        selected = (
            next((name for name, data in cfg.accounts.items() if data["email"] == email), None)
            if email
            else None
        )
        if email and not selected:
            raise HTTPException(422, "Account is not configured")
        ref_profiles: set[str] = set()
        for ref in refs:
            try:
                ref_profiles.add(store.asset_get(ref)["profile"])
            except KeyError:
                if not allow_native:
                    raise HTTPException(
                        422, "Reference is not registered with this service"
                    ) from None
                if not selected:
                    raise HTTPException(
                        422, "Native references require an explicit configured account"
                    ) from None
        if len(ref_profiles) > 1 or (selected and ref_profiles and selected not in ref_profiles):
            raise HTTPException(422, "References must belong to the selected account")
        if ref_profiles:
            owner = next(iter(ref_profiles))
            if owner not in cfg.accounts:
                raise HTTPException(422, "Reference account is not configured")
            return owner
        if selected:
            return selected
        from gflow_cli.selfhost.account_scheduler import select_account
        from gflow_cli.selfhost.model_quarantine import NoEligibleAccount

        try:
            if operation is None:
                return select_account(store, cfg.accounts)
            return select_account(store, cfg.accounts, operation=operation, model_key=model_key)
        except NoEligibleAccount as exc:
            raise NoEligibleAccountHTTPError(exc) from None
        except ValueError:
            raise HTTPException(503, "No current verified accounts configured") from None

    def check_unknown(payload: dict[str, Any], allowed: set[str]) -> None:
        unknown = sorted(set(payload) - allowed)
        if unknown:
            feature_missing(",".join(unknown))
        if "projectId" in payload:
            payload["projectId"] = uuid_value(payload["projectId"], "projectId")

    def native_video_controls(payload: dict[str, Any]) -> None:
        """Canonicalize existing controls without treating explicit invalid values as omitted."""
        if "modelKey" in payload and (
            not isinstance(payload["modelKey"], str) or not 1 <= len(payload["modelKey"]) <= 200
        ):
            raise HTTPException(422, "modelKey requires a bounded native model key")
        if "aspectRatio" in payload:
            aspect = payload["aspectRatio"]
            if not isinstance(aspect, str):
                raise HTTPException(422, "Invalid native video aspect ratio")
            payload["aspectRatio"] = {"landscape": "16:9", "portrait": "9:16"}.get(aspect, aspect)
            if payload["aspectRatio"] not in ("16:9", "9:16", "1:1"):
                raise HTTPException(422, "Invalid native video aspect ratio")
        if payload.get("resolution") == "4K":
            payload["resolution"] = "4k"

    async def translate_input_aliases(
        payload: dict[str, Any], fields: dict[str, str], *, confirmed_delete: bool = False
    ) -> dict[str, str]:
        """Resolve exact mappings and fresh declarations before durable submission."""
        bindings: list[tuple[str, NativeAlias | NativeResourceAlias]] = []
        for field, expected in fields.items():
            value = payload.get(field)
            if not isinstance(value, str) or not value.startswith("user:"):
                continue
            binding: NativeAlias | NativeResourceAlias | None
            try:
                binding = aliases.get(value)
            except ValueError:
                try:
                    binding = resource_aliases.get(value)
                except ValueError:
                    raise HTTPException(400, "Unsupported composite input shape") from None
            if binding is None:
                raise HTTPException(404, "Composite input mapping not found")
            allowed = (
                {"image", "character"}
                if expected == "image-or-character"
                else {"image", "video", "audio"}
                if expected == "media"
                else {expected}
            )
            if binding.kind not in allowed:
                raise HTTPException(400, "Composite input has the wrong resource kind")
            verified_alias_account(binding)
            bindings.append((field, binding))
        if not bindings:
            return {}
        first = bindings[0][1]
        scope = (first.profile, first.account, first.project_id)
        if any((b.profile, b.account, b.project_id) != scope for _, b in bindings):
            raise HTTPException(409, "Composite inputs require one account and project scope")
        if payload.get("email") is not None and payload["email"] != first.account:
            raise HTTPException(403, "Composite input belongs to another account")
        if payload.get("projectId") is not None and (
            uuid_value(payload["projectId"], "projectId") != first.project_id
        ):
            raise HTTPException(403, "Composite input belongs to another project")
        from gflow_cli.api.transports.native_asset_lookup import media_url

        metadata: dict[tuple[str, str, str], dict[str, Any]] = {}
        replacements: dict[str, str] = {}
        for field, binding in bindings:
            identifier = binding.media_id if isinstance(binding, NativeAlias) else binding.native_id
            key = (binding.kind, binding.project_id, identifier)
            if confirmed_delete and isinstance(binding, NativeAlias):
                # Only a confirmed, exact scoped receipt can replace fresh asset proof.
                # The permanent-delete worker re-verifies live account/project ownership.
                import hashlib

                from gflow_cli.api.native_delete_receipts import DeleteReceipts
                from gflow_cli.auth import profile_dir
                from gflow_cli.selfhost.account_marker import read_verified_account

                location = profile_dir(binding.profile)
                verified_email = read_verified_account(location)
                owner = (
                    hashlib.sha256(verified_email.casefold().encode("utf-8")).hexdigest()
                    if verified_email is not None
                    else None
                )
                receipt_root = (
                    location / ".gflow_delete_receipts" / owner / binding.project_id
                    if owner is not None
                    else None
                )
                if owner is not None and receipt_root is not None and receipt_root.exists():
                    try:
                        receipt_kind = DeleteReceipts(location, owner, binding.project_id).kind(
                            identifier
                        )
                    except (ValueError, OSError):
                        raise HTTPException(409, "Confirmed delete receipt is invalid") from None
                    if receipt_kind == binding.kind:
                        replacements[field] = identifier
                        continue
            if key not in metadata:
                metadata[key] = (
                    await native_alias_metadata(binding.profile, binding.project_id, identifier)
                    if isinstance(binding, NativeAlias)
                    else await resource_alias_metadata(binding)
                )
            row = metadata[key]
            if isinstance(binding, NativeAlias):
                if row.get("kind") != binding.kind:
                    raise HTTPException(502, "Composite input native media kind changed")
                try:
                    media_url(row.get("url"), binding.kind)
                except ValueError:
                    raise HTTPException(502, "Composite input fresh URL is unavailable") from None
            else:
                verify_resource_declarations(binding, row, registration=False)
            replacements[field] = identifier
        verified_alias_account(first)
        payload.update(replacements)
        payload["email"] = first.account
        payload["projectId"] = first.project_id
        return replacements

    def uuid_value(value: Any, label: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            raise HTTPException(422, f"{label} must be a bare Google Flow UUID") from None

    async def cache_alias_images(payload: dict[str, Any], identifiers: list[str]) -> None:
        """Materialize only freshly verified aliases in a private scoped image cache."""
        if not identifiers:
            return
        profile = pick_account(payload.get("email"), [], allow_native=True)
        project = uuid_value(payload["projectId"], "projectId")
        for identifier in dict.fromkeys(identifiers):
            try:
                current = store.asset_get(identifier)
            except KeyError:
                current = None
            if current is not None:
                if (current["profile"], current["project"]) != (profile, project):
                    raise HTTPException(
                        422, "Reference cache belongs to another account or project"
                    )
                if current["mime"] not in ("image/png", "image/jpeg"):
                    raise HTTPException(422, "Video image inputs must be PNG or JPEG assets")
                continue
            parent = cfg.root / "native-image-cache" / profile / project
            if not parent.resolve().is_relative_to(cfg.root.resolve()):
                raise HTTPException(502, "Native image cache unavailable")
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output_dir = parent / str(uuid.uuid4())
            output_dir.mkdir(mode=0o700)
            published = False
            try:
                code, raw = await subprocess_run(
                    [
                        sys.executable,
                        "-m",
                        "gflow_cli.selfhost.native_worker",
                        "asset-cache-image",
                        profile,
                        json.dumps(
                            {
                                "project_id": project,
                                "media_id": identifier,
                                "output_dir": str(output_dir),
                            }
                        ),
                    ],
                    60,
                )
                result = parse_json_output(raw)
                if (
                    code
                    or result.get("status") != "ok"
                    or result.get("kind") != "image"
                    or result.get("mediaGenerationId") != identifier
                    or result.get("projectId") != project
                    or result.get("mimeType") not in ("image/png", "image/jpeg")
                    or type(result.get("bytes")) is not int
                    or not 0 < result["bytes"] <= MAX_ASSET
                ):
                    raise ValueError("Invalid native image cache result")
                image_path = contained_file(str(result.get("path", "")), output_dir)
                if (
                    image_path.parent != output_dir.resolve()
                    or image_path.stat().st_size != result["bytes"]
                ):
                    raise ValueError("Invalid native image cache bytes")
                from PIL import Image

                with Image.open(image_path) as image:
                    expected = "PNG" if result["mimeType"] == "image/png" else "JPEG"
                    if image.format != expected:
                        raise ValueError("Invalid native image cache MIME")
                    image.verify()
                with Image.open(image_path) as image:
                    image.load()
                published = store.asset_cache_if_scope(
                    identifier, profile, project, str(image_path), result["mimeType"]
                )
            except HTTPException:
                raise
            except (ValueError, KeyError, OSError):
                raise HTTPException(502, "Native image cache unavailable") from None
            finally:
                if not published:
                    shutil.rmtree(output_dir)

    async def enqueue(
        request: Request,
        kind: str,
        payload: dict[str, Any],
        profile: str,
        captcha_token: str | None = None,
    ) -> dict[str, Any]:
        asynchronous = payload.pop("async", False)
        if type(asynchronous) is not bool:
            raise HTTPException(422, "async must be a boolean")
        if "replyRef" in payload and (
            not isinstance(payload["replyRef"], str) or len(payload["replyRef"]) > 4096
        ):
            raise HTTPException(422, "replyRef must be a string of at most 4096 characters")
        payload["_delivery_async"] = asynchronous
        if "replyUrl" in payload and not isinstance(payload["replyUrl"], str):
            raise HTTPException(422, "replyUrl must be a string")
        if payload.get("replyUrl"):
            try:
                validate_callback(payload["replyUrl"], cfg.callbacks)
            except (ValueError, TypeError):
                raise HTTPException(422, "Invalid or disallowed replyUrl") from None
        idem = request.headers.get("idempotency-key")
        if idem and len(idem) > 128:
            raise HTTPException(422, "Idempotency-Key is too long")
        existing = store.by_idempotency(idem) if idem else None
        if existing:
            profile = existing["profile"]
            default_project = json.loads(existing["payload"])["project"]
        else:
            if profile not in cfg.accounts:
                raise HTTPException(409, "Account registration changed before submission")
            default_project = cfg.accounts[profile]["project"]
        if profile not in cfg.accounts:
            raise HTTPException(
                409, "Account registration changed; inspect the account before retrying"
            )
        payload["project"] = uuid_value(payload.get("projectId", default_project), "projectId")
        owned_secret: Path | None = None
        if captcha_token is not None and existing is None:
            secret = payload["captchaSecret"]
            if store.control_used(secret):
                raise HTTPException(409, "Supplied CAPTCHA token already belongs to another job")
            from gflow_cli.selfhost.captcha_routes import prepare_image_controls

            try:
                prepared: dict[str, Any] = {"captchaToken": captcha_token}
                prepare_image_controls(prepared, cfg.root)
                owned_secret = Path(prepared["captchaSecret"])
            except FileExistsError:
                raise HTTPException(409, "Supplied CAPTCHA token is already pending") from None
        try:
            job = store.submit(kind, profile, payload, idem)
        except ValueError as exc:
            if owned_secret:
                owned_secret.unlink(missing_ok=True)
            raise HTTPException(409, str(exc)) from None
        except OverflowError:
            if owned_secret:
                owned_secret.unlink(missing_ok=True)
            raise HTTPException(429, "Queue is full", headers={"Retry-After": "30"}) from None
        except Exception:
            if owned_secret:
                owned_secret.unlink(missing_ok=True)
            raise

        return job

    async def submit(
        request: Request,
        kind: str,
        payload: dict[str, Any],
        profile: str,
        captcha_token: str | None = None,
    ) -> dict[str, Any] | JSONResponse:
        from gflow_cli.selfhost.http_jobs import error_record, http_status, result_record

        if kind in {
            "images/upscale",
            "videos",
            "videos/extend",
            "videos/edit",
            "videos/reference",
            "videos/promote",
            "voices/create",
        } and any(key in payload for key in ("captchaToken", "captchaOrder", "captchaRetry")):
            from gflow_cli.selfhost.captcha_routes import prepare_image_controls

            raw_token = payload.get("captchaToken")
            if "captchaToken" in payload:
                from gflow_cli.api.native_captcha import validate_native_captcha_token
                from gflow_cli.errors import ConfigurationError

                try:
                    validate_native_captcha_token(raw_token)
                except ConfigurationError:
                    raise HTTPException(
                        422, "captchaToken requires one bounded token without whitespace"
                    ) from None
            prepare_image_controls(payload, cfg.root, persist_token=False, native_retry=True)
            captcha_token = raw_token if isinstance(raw_token, str) else None
        asynchronous = payload.get("async", False)
        job = await enqueue(request, kind, payload, profile, captcha_token)
        identifier = job["jobId"]
        location = f"{prefix}/jobs/{identifier}"
        if asynchronous:
            return JSONResponse(
                store.get_record(identifier), status_code=201, headers={"Location": location}
            )
        budget = min(cfg.sync_wait, 180 if kind == "videos/concatenate" else 600)
        deadline = time.monotonic() + budget
        while job["status"] in ("created", "running") and time.monotonic() < deadline:
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
            job = store.get(identifier)
        # A final read handles completion racing the wait deadline.
        job = store.get(identifier)
        if job["status"] == "completed":
            return {"jobId": identifier, "status": "completed", **result_record(job)}
        if job["status"] in ("failed", "interrupted"):
            return JSONResponse(
                {"jobId": identifier, **result_record(job), **error_record(job, job["status"])},
                status_code=http_status(job, job["status"]),
                headers={"Location": location},
            )
        return JSONResponse(
            {
                **result_record(job),
                "jobId": identifier,
                "jobid": identifier,
                "status": store.get_record(identifier)["status"],
                "error": (
                    "Synchronous wait expired; poll this existing job before another submission."
                ),
                "code": 408,
                "processingContinues": True,
                "retryable": False,
            },
            status_code=408,
            headers={"Location": location},
        )

    def pagination(request: Request) -> tuple[int, str | None]:
        try:
            limit = int(request.query_params.get("limit", "100"))
        except ValueError:
            raise HTTPException(422, "limit must be an integer") from None
        cursor = request.query_params.get("cursor")
        if not 1 <= limit <= 100 or cursor is not None and len(cursor) > 512:
            raise HTTPException(422, "limit must be 1 to 100 and cursor at most 512 characters")
        return limit, cursor

    def page_slice(request: Request, rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
        limit, cursor = pagination(request)
        offset = 0
        if cursor:
            try:
                decoded: Any = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                offset = decoded["offset"]
                if type(offset) is not int or not 0 <= offset <= 10000:
                    raise ValueError("Invalid offset")
            except Exception:
                raise HTTPException(422, "Invalid list cursor") from None
        selected = rows[offset : offset + limit]
        next_cursor = (
            base64.urlsafe_b64encode(json.dumps({"offset": offset + limit}).encode()).decode()
            if offset + limit < len(rows)
            else None
        )
        return {field: selected, "cursor": next_cursor}

    def account_metadata(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile": row["profile"],
            "email": row["email"],
            "projectId": row["project"],
            "health": "OK" if row["enabled"] == 1 and row["verified"] else "LOGIN_REQUIRED",
            "enabled": bool(row["enabled"]),
            "healthSource": (
                "verified imported identity and native project access"
                if row["verification_source"] == "native-cookie-verified"
                else "operator-attested local profile registration"
            ),
            "verificationSource": row["verification_source"],
            "created": datetime.fromtimestamp(row["created"], UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "updated": datetime.fromtimestamp(
                store.account_updated(row["profile"], row["email"], row["created"]), UTC
            )
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "scope": "local-profile-registration",
            "idleSessionMaintenance": store.idle_session_status(
                row["profile"], cfg.idle_session_interval
            ),
            "sessionStatus": store.session_status(row["profile"], cfg.idle_session_interval),
        }

    @app.post(
        prefix + "/accounts/{email}/health", response_model=None, openapi_extra=FORM_REQUEST_BODY
    )
    async def account_health(
        request: Request, email: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        # This read-only operation shares the durable serial queue with generation.
        # Never open a competing browser from a request handler or change auth flags.
        check_unknown(payload, {"async", "replyRef", "replyUrl"})
        profile = pick_account(email, [])
        payload["email"] = cfg.accounts[profile]["email"]
        payload["projectId"] = cfg.accounts[profile]["project"]
        return await submit(request, "accounts/health", payload, profile)

    async def register_cookie_account(payload: dict[str, Any]) -> JSONResponse:
        from gflow_cli.auth import default_profile_root, profile_dir
        from gflow_cli.errors import AuthMissingError, ConfigurationError, ProfileLockedError
        from gflow_cli.profile_lease import ProfileLease
        from gflow_cli.selfhost.account_import import reverify_imported_project
        from gflow_cli.selfhost.account_marker import read_verified_account
        from gflow_cli.selfhost.profile_import import (
            discard_imported_profile,
            import_cookie_profile,
        )
        from gflow_cli.selfhost.receipt_refresh import carry_delete_receipts
        from gflow_cli.selfhost.session_import import CookieTableError, parse_cookie_table

        check_unknown(payload, {"cookies", "email", "profile", "projectId"})
        try:
            table = parse_cookie_table(payload.get("cookies"))
        except CookieTableError:
            raise HTTPException(400, "Invalid or expired DevTools cookie table") from None
        email = payload.get("email")
        if email is not None and (not isinstance(email, str) or not 1 <= len(email) <= 254):
            raise HTTPException(400, "email requires a valid account handle")
        profile = payload.get("profile", "cookie_" + uuid.uuid4().hex)
        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", profile):
            raise HTTPException(400, "profile requires a safe new profile name")
        target = profile_dir(profile)
        if (
            target.exists()
            or target.is_symlink()
            or target.parent.resolve() != default_profile_root().resolve()
        ):
            raise HTTPException(409, "Cookie import requires a new profile")
        old = store.account_lookup(email) if email else None
        project = uuid_value(payload["projectId"], "projectId") if "projectId" in payload else None
        if old and project is not None and project != old["project"]:
            raise HTTPException(400, "Cookie refresh preserves the existing project")
        expected_email = email
        if old:
            if store.profile_busy(old["profile"]):
                raise HTTPException(409, "Account has an accepted or running job")
            try:
                async with ProfileLease(profile_dir(old["profile"])):
                    expected_email = read_verified_account(profile_dir(old["profile"]))
            except ProfileLockedError:
                raise HTTPException(409, "Original account profile is in use") from None
            if expected_email is None:
                raise HTTPException(
                    400, "Original account identity is unavailable; complete login first"
                )
            project = old["project"]
        elif expected_email is not None and not re.fullmatch(
            r'[^\s"<>]{1,128}@[^\s"<>]{1,125}', expected_email
        ):
            raise HTTPException(400, "A new imported account requires an actual email identity")
        imported = None
        activated = False
        cleanup_pending = False
        preserved_receipts = 0
        failure: HTTPException | None = None
        try:
            imported = await import_cookie_profile(
                table, profile, expected_email=expected_email, project_id=project
            )
            if imported.profile != profile:
                raise ConfigurationError(detail="Import returned an unrelated profile")
            if old is None:
                # Cookies-only requests identify an existing account from proven identity,
                # including legacy public aliases whose private marker matches it.
                matches: list[dict[str, Any]] = []
                for account_row in store.accounts():
                    actual = read_verified_account(profile_dir(account_row["profile"]))
                    if actual and actual.casefold() == imported.email.casefold():
                        matches.append(account_row)
                if len(matches) > 1:
                    raise ValueError("Imported identity matches multiple account registrations")
                old = matches[0] if matches else store.account_lookup(imported.email)
                if old:
                    if store.profile_busy(old["profile"]):
                        raise ValueError("Original account became busy during import")
                    if imported.project_id != old["project"]:
                        imported = await reverify_imported_project(imported, old["project"])
            if (
                old
                and expected_email is not None
                and imported.email.casefold() != expected_email.casefold()
            ):
                raise AuthMissingError(
                    detail="Imported identity does not match the original account"
                )
            selected_email = old["email"] if old else imported.email
            selected_project = old["project"] if old else imported.project_id
            async with AsyncExitStack() as leases:
                names: set[str] = {profile}
                if old:
                    names.add(str(old["profile"]))
                for name in sorted(names):
                    await leases.enter_async_context(ProfileLease(profile_dir(name)))
                if (
                    not imported.matches_private_state(target)
                    or read_verified_account(target) != imported.email
                ):
                    raise ValueError("Imported profile changed before activation")
                if old:
                    actual = read_verified_account(profile_dir(old["profile"]))
                    if not actual or actual.casefold() != imported.email.casefold():
                        raise ValueError("Original account identity changed during import")
                if old:
                    preserved_receipts = carry_delete_receipts(
                        profile_dir(old["profile"]), target, imported.email
                    )
                store.account_activate_import(
                    profile, selected_email, selected_project, expected_old=old
                )
                activated = True
                if old:
                    cfg.accounts.pop(old["profile"], None)
                cfg.accounts[profile] = {"email": selected_email, "project": selected_project}
            old_task = worker_tasks.pop(old["profile"], None) if old else None
            # Publish the new worker before any cancellable await after activation.
            # A disconnected refresh request must not leave its durable account idle.
            if start_workers:
                worker_tasks[profile] = asyncio.create_task(worker(cfg, store, profile))
            if old_task:
                old_task.cancel()
                await asyncio.gather(old_task, return_exceptions=True)
            row = store.account_lookup(selected_email)
            assert row is not None
            return JSONResponse(
                {
                    **account_metadata(row),
                    "cookieCount": imported.cookie_count,
                    "preservedDeleteReceipts": preserved_receipts,
                    "browserProfileDeleted": False,
                },
                status_code=200 if old else 201,
            )
        except ProfileLockedError:
            failure = HTTPException(
                409, "An account profile is in use; registration was not changed"
            )
            raise failure from None
        except (ValueError, sqlite3.IntegrityError):
            failure = HTTPException(
                409, "Account changed or became busy during import; registration preserved"
            )
            raise failure from None
        except (ConfigurationError, AuthMissingError):
            failure = HTTPException(
                400, "Cookies did not verify the expected identity and Flow project access"
            )
            raise failure from None
        finally:
            if imported is not None and imported.profile == profile and not activated:
                try:
                    cleanup_pending = not await discard_imported_profile(imported)
                except Exception:
                    cleanup_pending = True
                # Changed or leased candidates are retained safely, never force-deleted.
                if cleanup_pending:
                    app.state.cookie_cleanup_pending = True
                    if failure is not None:
                        # FastAPI accepts JSON detail although its attribute is typed str.
                        cast(Any, failure).detail = {
                            "message": failure.detail,
                            "cleanupPending": True,
                            "candidateProfile": profile,
                        }

    @app.post(prefix + "/accounts", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def register_account(
        payload: Annotated[dict[str, Any], Depends(parse_payload)],
    ) -> dict[str, Any] | JSONResponse:
        if "cookies" in payload:
            return await register_cookie_account(payload)
        check_unknown(payload, {"profile", "email", "projectId", "enabled", "verified"})
        profile, email = payload.get("profile"), payload.get("email")
        if not isinstance(profile, str) or not re.fullmatch(r"[\w-]{1,128}", profile):
            raise HTTPException(422, "profile requires a safe existing profile name")
        if not isinstance(email, str) or not 1 <= len(email) <= 254:
            raise HTTPException(422, "email requires an account handle")
        project = uuid_value(payload.get("projectId"), "projectId")
        enabled, verified = payload.get("enabled", False), payload.get("verified", False)
        if type(enabled) is not bool or type(verified) is not bool:
            raise HTTPException(422, "enabled and verified must be booleans")
        if enabled and not verified:
            raise HTTPException(422, "An enabled profile requires explicit operator verification")
        from gflow_cli.auth import default_profile_root, profile_dir

        location = profile_dir(profile).resolve()
        if not location.is_relative_to(default_profile_root().resolve()) or not location.is_dir():
            raise HTTPException(
                422, "Profile does not exist; complete local hosted-browser login first"
            )
        if not enabled:
            # Allow stopping pending maintenance without canceling accepted operator work.
            remaining_profiles = {
                key: value for key, value in cfg.accounts.items() if key != profile
            }
            store.cancel_idle_health(cfg.idle_session_interval, remaining_profiles)
        if store.profile_busy(profile):
            raise HTTPException(409, "Profile has an accepted or running job")
        try:
            store.account_set(profile, email, project, enabled, verified)
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "Account handle is already registered to another profile"
            ) from None
        except ValueError:
            raise HTTPException(
                409,
                "A deleted account registration requires a fresh logical profile; "
                "the existing browser profile is preserved",
            ) from None
        if enabled:
            cfg.accounts[profile] = {"email": email, "project": project}
            if start_workers and profile not in worker_tasks:
                worker_tasks[profile] = asyncio.create_task(worker(cfg, store, profile))
        else:
            cfg.accounts.pop(profile, None)
        row = next(row for row in store.accounts() if row["profile"] == profile)
        return account_metadata(row)

    @app.delete(prefix + "/accounts/{email}")
    async def unregister_account(email: str) -> dict[str, Any]:
        row = next((row for row in store.accounts() if row["email"] == email), None)
        if row is None:
            raise HTTPException(404, "Account is not registered")
        if store.profile_busy(row["profile"]):
            raise HTTPException(409, "Account has an accepted or running job")
        store.account_delete(row["profile"])
        cfg.accounts.pop(row["profile"], None)
        return {
            "email": email,
            "removed": True,
            "scope": "local-registration",
            "browserProfileDeleted": False,
        }

    @app.get(prefix + "/accounts")
    async def accounts() -> dict[str, Any]:
        return {row["email"]: account_metadata(row) for row in store.accounts()}

    @app.get(prefix + "/accounts/{email}")
    async def account(email: str) -> dict[str, Any]:
        all_accounts = await accounts()
        if email not in all_accounts:
            raise HTTPException(404, "Account is not configured")
        return all_accounts[email]

    @app.get(prefix + "/capabilities")
    async def capabilities() -> dict[str, Any]:
        return {
            "implemented": [
                "accounts/read",
                "accounts/cookie-import",
                "accounts/project-access-health",
                "accounts/register-local",
                "accounts/unregister-local",
                "captcha-providers/configuration",
                "captcha-stats",
                "requests/multipart-text-fields",
                "captcha-google-confirmed-waf-only-retries",
                "images/provider-captcha-generation",
                "images/upscale-provider-controls",
                "videos/generic-count1-through4-provider-controls",
                "assets/resources-observed-account-continuation",
                "assets/upload-webp-conversion",
                "accounts/score-and-local-quota-selection",
                "images/seed",
                "images/canonical-references",
                "images/canonical-characters",
                "images/aspectRatio-auto-local-policy",
                "images/supplied-captcha-token",
                "native-reference-video/supplied-captcha-token",
                "native-edit-video/supplied-captcha-token",
                "native-extension/supplied-captcha-token",
                "videos/upscale-native-promotion",
                "native-tts/supplied-captcha-token",
                "images",
                "images/upscale",
                "assets/upload",
                "assets/upload-mp4",
                "assets/media-native-timeline",
                "assets/media-native-attached-inventory",
                "assets/verified-composite-read-mappings",
                "aliases/verified-generation-inputs",
                "characters/verified-composite-read-mappings",
                "voices/verified-composite-read-mappings",
                "assets/media-native-upload-and-source-time",
                "assets/archive-native-whole-batch",
                "assets/delete-native-individual",
                "assets/delete-local-cache",
                "assets/read",
                "assets/download",
                "assets/projects",
                "assets/projects-native",
                "assets/projects-native-account-history",
                "assets/projects-observed-history-synchronization",
                "assets/media",
                "jobs",
                "voices/read-system",
                "voices/read-system-native",
                "voices/custom-saved-tts",
                "characters/voice-binding",
                "characters/read-native-project",
                "characters/create-native-image-reference",
                "characters/second-image-reference",
                "characters/edit-native-metadata",
                "characters/delete-native",
                "callbacks",
                "idempotency",
            ],
            "videoEnabled": cfg.allow_video,
            "videoAdapters": [
                "videos/text-to-video",
                "videos/start-end-images",
                "videos/image-ingredients",
                "videos/count-checkpoints",
                "videos/upscale",
                "videos/gif",
                "videos/concatenate",
                "videos/extend-native-discovered-model",
                "videos/omni-native-edit",
                "videos/omni-native-reference-audio",
            ],
            "notImplemented": [
                "videos/seed",
                "images/aspectRatio-auto-native",
            ],
            "localPolicies": {
                "images/aspectRatio-auto": {
                    "policy": "derived-first-reference-nearest-supported-v1",
                    "nativeGoogleAuto": False,
                    "requires": "first-owned-image-reference",
                }
            },
            "verificationPending": [
                "accounts/cookie-import-live-acceptance",
                "captcha-provider-google-acceptance",
                "videos/generic-multi-output-rendering",
                "images/ten-reference-rendering",
                "images/4k-entitlement-and-rendering",
            ],
            "verification": "Adapters require live verification per account and operation",
        }

    @app.post(prefix + "/images", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def images(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        allowed = {
            "prompt",
            "email",
            "model",
            "aspectRatio",
            "count",
            "replyUrl",
            "replyRef",
            "async",
            "projectId",
            "seed",
            "captchaToken",
            "captchaRetry",
            "captchaOrder",
        }
        allowed.update(f"reference_{i}" for i in range(1, 11))
        allowed.update(f"character_{i}" for i in range(1, 8))
        check_unknown(payload, allowed)
        if (
            not isinstance(payload.get("prompt"), str)
            or not 1 <= len(payload["prompt"].strip()) <= 4000
        ):
            raise HTTPException(422, "prompt requires 1 to 4000 characters")
        model = payload.setdefault("model", "nano-banana-2-lite")
        if isinstance(model, str):
            model = payload["model"] = {
                "nano-banana": "nano-banana-2",
                "imagen-4": "nano-banana-2-lite",
            }.get(model, model)
        if not isinstance(model, str) or model not in MODEL_ALIASES:
            raise HTTPException(422, "Unsupported image model")
        count = payload.setdefault("count", 4)
        if type(count) is not int or not 1 <= count <= 4:
            raise HTTPException(422, "count requires an integer from 1 to 4")
        await translate_input_aliases(
            payload,
            {
                **{f"reference_{i}": "image" for i in range(1, 11)},
                **{f"character_{i}": "character" for i in range(1, 8)},
            },
        )
        refs: list[str] = []
        for i in range(1, 11):
            key = f"reference_{i}"
            if key in payload:
                payload[key] = uuid_value(payload[key], key)
                refs.append(payload[key])
        from gflow_cli.api.reference_markers import (
            ReferenceContractError,
            ReferenceSlot,
            reference_plan_record,
            resolve_reference_markers,
        )

        slots = {
            f"reference_{i}": ReferenceSlot("image", payload[f"reference_{i}"])
            for i in range(1, 11)
            if f"reference_{i}" in payload
        }
        for i in range(1, 8):
            key = f"character_{i}"
            if key in payload:
                payload[key] = uuid_value(payload[key], key)
                slots[key] = ReferenceSlot("character", payload[key])
        try:
            plan = resolve_reference_markers(payload["prompt"], slots=slots, surface="image")
        except ReferenceContractError:
            raise HTTPException(400, "Invalid or unresolved image reference marker") from None
        payload["reference_syntax"] = "slots"
        payload["reference_prompt_plan"] = reference_plan_record(plan)
        if "seed" in payload and (
            type(payload["seed"]) is not int or not 0 <= payload["seed"] <= 2147483647 - count + 1
        ):
            raise HTTPException(
                422, "seed must be a nonnegative integer with room for count consecutive seeds"
            )
        refs = list(plan.image_ids)
        profile = pick_account(payload.get("email"), refs, allow_native=True, operation="images")
        managed_assets: dict[str, dict[str, Any]] = {}
        sources: list[dict[str, str]] = []
        for ref in refs:
            try:
                asset = store.asset_get(ref)
            except KeyError:
                sources.append({"id": ref, "kind": "native"})
            else:
                if asset["mime"] not in ("image/png", "image/jpeg"):
                    raise HTTPException(422, "Image references must be PNG or JPEG assets")
                managed_assets[ref] = asset
                sources.append({"id": ref, "kind": "managed"})
        payload["_image_reference_sources"] = sources
        default_aspect = (
            "auto" if refs and model in ("nano-banana-2", "nano-banana-pro") else "16:9"
        )
        requested_aspect = payload.setdefault("aspectRatio", default_aspect)
        if isinstance(requested_aspect, str):
            requested_aspect = payload["aspectRatio"] = {
                "landscape": "16:9",
                "portrait": "9:16",
            }.get(requested_aspect, requested_aspect)
        if requested_aspect == "auto":
            if not refs:
                raise HTTPException(422, "aspectRatio auto requires an actual reference image")
            from gflow_cli.api.image_aspect_policy import derive_aspect_from_file

            first = managed_assets.get(refs[0])
            if first is None:
                # Native dimensions are checked in the serialized selected-account worker.
                payload["requestedAspectRatio"] = "auto"
            else:
                if first["profile"] != profile:
                    raise HTTPException(422, "Auto reference must belong to the selected account")
                uuid_value(first["project"], "Registered reference project")
                try:
                    path = contained_file(first["path"], cfg.root)
                    decision = await run_in_threadpool(derive_aspect_from_file, path)
                except ValueError:
                    raise HTTPException(
                        422, "Auto requires a valid managed PNG or JPEG reference"
                    ) from None
                payload.update(
                    aspectRatio=decision.resolved_aspect,
                    requestedAspectRatio=decision.requested_aspect,
                    resolvedAspectRatio=decision.resolved_aspect,
                    aspectPolicy=decision.policy,
                )
        elif requested_aspect not in ("16:9", "4:3", "1:1", "3:4", "9:16"):
            feature_missing("aspectRatio")
        from gflow_cli.selfhost.captcha_routes import prepare_image_controls

        supplied_token = payload.get("captchaToken")
        prepare_image_controls(payload, cfg.root, persist_token=False, native_retry=True)
        return await submit(
            request,
            "images",
            payload,
            profile,
            captcha_token=supplied_token if isinstance(supplied_token, str) else None,
        )

    @app.post(prefix + "/images/upscale", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def upscale(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        check_unknown(
            payload,
            {
                "captchaToken",
                "captchaOrder",
                "captchaRetry",
                "mediaGenerationId",
                "resolution",
                "email",
                "projectId",
                "replyUrl",
                "replyRef",
                "async",
            },
        )
        await translate_input_aliases(payload, {"mediaGenerationId": "image"})
        payload["mediaGenerationId"] = uuid_value(
            payload.get("mediaGenerationId"), "mediaGenerationId"
        )
        if payload.setdefault("resolution", "2k") not in ("2k", "4k"):
            raise HTTPException(422, "resolution requires 2k or 4k")
        try:
            asset = store.asset_get(payload["mediaGenerationId"])
        except KeyError:
            asset = None
        profile = pick_account(
            payload.get("email"), [payload["mediaGenerationId"]] if asset else []
        )
        if not asset and len(cfg.accounts) > 1 and not payload.get("email"):
            raise HTTPException(422, "Unregistered image requires an explicit account")
        if asset:
            if asset["mime"] not in ("image/png", "image/jpeg"):
                raise HTTPException(422, "Image upscale requires an image asset")
            if payload.get("projectId") and payload["projectId"] != asset["project"]:
                raise HTTPException(422, "projectId does not own the requested media")
            payload["projectId"] = asset["project"]
        return await submit(request, "images/upscale", payload, profile)

    @app.post(prefix + "/assets")
    @app.post(prefix + "/assets/{email}")
    async def upload(request: Request, email: str | None = None) -> dict[str, Any]:
        mime = request.headers.get("content-type", "").split(";")[0]
        if mime not in ("image/png", "image/jpeg", "image/webp", "video/mp4"):
            raise HTTPException(415, "Upload requires raw PNG, JPEG, WebP or MP4")
        rights = request.headers.get("x-flow-rights-confirmed")
        if rights is not None and (rights not in ("true", "false") or mime != "video/mp4"):
            raise HTTPException(
                422, "X-Flow-Rights-Confirmed requires true or false on MP4 uploads only"
            )
        if mime == "video/mp4" and rights != "true":
            raise HTTPException(422, "MP4 uploads require X-Flow-Rights-Confirmed: true")
        profile = pick_account(email, [])
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > MAX_ASSET:
                raise HTTPException(413, "Asset exceeds 20 MiB")
        source_mime = mime
        converted = False
        if mime == "image/webp":
            from gflow_cli.selfhost.image_upload import prepare_image_upload

            try:
                prepared = prepare_image_upload(bytes(data), mime)
            except ValueError:
                raise HTTPException(422, "Invalid or unsupported WebP upload") from None
            data = bytearray(prepared.data)
            mime = prepared.content_type
            converted = prepared.converted
        valid = (
            data.startswith(b"\x89PNG\r\n\x1a\n")
            if mime == "image/png"
            else len(data) >= 12 and bytes(data[4:8]) == b"ftyp"
            if mime == "video/mp4"
            else data.startswith(b"\xff\xd8\xff")
        )
        if not valid:
            raise HTTPException(422, "Asset signature does not match content type")
        directory = cfg.root / "uploads"
        directory.mkdir(exist_ok=True)
        path = directory / (
            hashlib.sha256(data).hexdigest()
            + (".png" if mime == "image/png" else ".mp4" if mime == "video/mp4" else ".jpg")
        )
        path.write_bytes(data)
        upload_payload: dict[str, Any] = {"input": str(path), "mime": mime}
        if mime == "video/mp4":
            upload_payload["rightsConfirmed"] = rights == "true"
        job = await enqueue(request, "assets", upload_payload, profile)
        # Keep tee's synchronous upload contract; disconnection leaves the job durable.
        deadline = time.monotonic() + cfg.timeout
        while time.monotonic() < deadline:
            result = store.get(job["jobId"])
            if result["status"] == "completed":
                return {
                    **result,
                    "contentType": mime,
                    "sourceContentType": source_mime,
                    "converted": converted,
                }
            if result["status"] in ("failed", "interrupted"):
                raise HTTPException(502, result.get("error", "Upload failed"))
            await asyncio.sleep(0.25)
        raise HTTPException(
            504,
            {
                "jobId": job["jobId"],
                "detail": "Upload is still tracked; poll this job before retrying",
            },
        )

    @app.get(prefix + "/jobs")
    async def jobs(request: Request) -> dict[str, Any]:
        source = request.query_params.get("source")
        if source not in (None, "local"):
            raise HTTPException(400, "Job source requires local for the durable job list")
        list_controls = {"email", "status", "kind", "limit", "cursor"}
        explicit_list = source == "local" or bool(list_controls & set(request.query_params))
        if "options" in request.query_params or not explicit_list:
            if set(request.query_params) - {"options"}:
                raise HTTPException(
                    400, "Statistics options cannot be combined with job-list filters"
                )
            from gflow_cli.selfhost.job_statistics import statistics

            try:
                return statistics(store, request.query_params.get("options", "summary"))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
        limit, cursor = pagination(request)
        status = request.query_params.get("status")
        if status and status not in (
            "created",
            "started",
            "running",
            "completed",
            "failed",
            "interrupted",
        ):
            raise HTTPException(422, "Unknown job status")
        email = request.query_params.get("email")
        profile = pick_account(email, []) if email else None
        try:
            return store.job_page(
                limit=limit,
                cursor=cursor,
                profile=profile,
                status="running" if status == "started" else status,
                kind=request.query_params.get("kind"),
            )
        except ValueError:
            raise HTTPException(422, "Invalid job cursor") from None

    @app.get(prefix + "/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        try:
            return store.get_record(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found") from None

    @app.post(prefix + "/assets/sync/{email}", openapi_extra=FORM_REQUEST_BODY)
    async def synchronize_inventory(
        email: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any]:
        """Fork extension: bounded read-only traversal with private resumable checkpoints."""
        from gflow_cli.selfhost.account_resource_routes import capture_bound_scope
        from gflow_cli.services.inventory_sync import validate_sync_options

        if set(payload) - {"maxSteps", "maxSeconds", "restart"}:
            raise HTTPException(422, "Unknown inventory sync controls")
        max_steps = payload.get("maxSteps", 10)
        max_seconds = payload.get("maxSeconds", 180)
        restart = payload.get("restart", False)
        try:
            validate_sync_options(max_steps, max_seconds, restart)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        profile = pick_account(email, [])
        expected_scope = capture_bound_scope(cfg, store, profile, email)
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "inventory-sync",
                profile,
                json.dumps(
                    {
                        "max_steps": max_steps,
                        "max_seconds": max_seconds,
                        "restart": restart,
                        "expected_account_sha256": expected_scope,
                    }
                ),
            ],
            max_seconds + 45,
        )
        if (
            pick_account(email, []) != profile
            or capture_bound_scope(cfg, store, profile, email) != expected_scope
        ):
            raise HTTPException(409, "Account scope changed during inventory synchronization")
        try:
            result = parse_json_output(raw)
            if code or result.get("status") != "ok" or result.get("complete") is not None:
                raise ValueError("Unavailable inventory synchronization")
            if (
                type(result.get("steps_read")) is not int
                or not 0 <= result["steps_read"] <= max_steps
                or type(result.get("traversal_finished")) is not bool
                or type(result.get("timed_out")) is not bool
                or not isinstance(result.get("observations"), dict)
                or not isinstance(result.get("resource_scopes"), dict)
            ):
                raise ValueError("Invalid inventory synchronization envelope")
        except ValueError:
            raise HTTPException(
                502, "Native inventory sync unavailable; committed progress retained"
            ) from None
        return result

    @app.get(prefix + "/assets/projects/{email}")
    async def projects(request: Request, email: str) -> dict[str, Any]:
        profile = pick_account(email, [])
        source = request.query_params.get("source", "history")
        if source not in ("local", "google", "history"):
            raise HTTPException(422, "source requires local, google or history")
        if source == "history":
            if set(request.query_params) - {"source", "cursor"}:
                raise HTTPException(422, "History summaries support cursor only")
            cursor = request.query_params.get("cursor")
            from gflow_cli.api.native_history import (
                validate_history_options,
                validate_history_summary_envelope,
            )

            try:
                validate_history_options(cursor, True, 50, 1000)
            except ValueError:
                raise HTTPException(422, "Invalid native history cursor") from None
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "history-list",
                    profile,
                    json.dumps(
                        {"all_pages": True, "max_pages": 50, "max_media": 1000, "cursor": cursor}
                    ),
                ],
                90,
            )
            try:
                result = parse_json_output(raw)
                if code or result.get("status") != "ok":
                    raise ValueError("Unavailable history")
                validate_history_summary_envelope(result)
                projects = result["project_summaries"]
                if not isinstance(projects, list):
                    raise ValueError("Invalid history summary")
                public_projects: list[dict[str, Any]] = []
                for candidate in cast(list[Any], projects):
                    if not isinstance(candidate, dict):
                        raise ValueError("Invalid history summary")
                    row = cast(dict[str, Any], candidate)
                    project = str(uuid.UUID(str(row["project_id"])))
                    if type(row.get("total")) is not int or row["total"] < 1:
                        raise ValueError("Invalid history summary count")
                    raw_types = row["by_type"]
                    if not isinstance(raw_types, dict):
                        raise ValueError("Invalid history summary types")
                    types = cast(dict[str, Any], raw_types)
                    if (
                        set(types) != {"image", "video"}
                        or any(type(value) is not int or value < 0 for value in types.values())
                        or sum(types.values()) != row["total"]
                    ):
                        raise ValueError("Invalid history summary types")
                    public_projects.append(
                        {
                            "projectId": project,
                            "isCurrent": project == cfg.accounts[profile]["project"],
                            "total": row["total"],
                            "byType": {key.upper(): value for key, value in types.items()},
                            **{
                                name: row[name]
                                for name in ("oldest", "newest")
                                if row.get(name) is not None
                            },
                        }
                    )
                if (
                    type(result.get("scanned")) is not int
                    or not 0 <= result["scanned"] <= 1000
                    or type(result.get("truncated")) is not bool
                    or sum(row["total"] for row in public_projects) > result["scanned"]
                ):
                    raise ValueError("Invalid history summary counters")
                if "media" in result and "workflows" in result:
                    observations.merge_history(profile, cfg.accounts[profile]["email"], result)
                return {
                    "email": email,
                    "projects": public_projects,
                    "scanned": result["scanned"],
                    "truncated": result["truncated"],
                    **({"cursor": result["cursor"]} if result.get("cursor") is not None else {}),
                    **(
                        {"stoppedOn": "timeBudget"}
                        if result.get("stopped_on") == "timeBudget"
                        else {}
                    ),
                    "complete": None,
                    "scope": (
                        "observed generated native account history; counts belong to this call"
                    ),
                }
            except (KeyError, TypeError, ValueError):
                raise HTTPException(502, "Native history summary unavailable") from None
        if source != "google" and any(
            key in request.query_params
            for key in (
                "allPages",
                "maxPages",
                "includeCatalogs",
                "catalogProjectIds",
                "maxProjects",
                "includeHistory",
                "historyCursor",
                "historyMaxPages",
                "historyMaxMedia",
            )
        ):
            raise HTTPException(422, "Traversal controls require source=google")
        if source == "google":
            raw_all = request.query_params.get("allPages", "false")
            if raw_all not in ("true", "false"):
                raise HTTPException(422, "allPages requires true or false")
            all_pages = raw_all == "true"
            raw_max = request.query_params.get("maxPages")
            try:
                max_pages = int(raw_max) if raw_max is not None else None
                validate_project_traversal(all_pages, max_pages)
            except ValueError:
                raise HTTPException(
                    422, "maxPages requires allPages=true and an integer 1 to 100"
                ) from None
            raw_include = request.query_params.get("includeCatalogs", "false")
            if raw_include not in ("true", "false"):
                raise HTTPException(422, "includeCatalogs requires true or false")
            include_catalogs = raw_include == "true"
            raw_projects = request.query_params.get("maxProjects")
            try:
                max_projects = int(raw_projects) if raw_projects is not None else None
                validate_project_catalogs(include_catalogs, max_projects)
            except ValueError:
                raise HTTPException(
                    422, "maxProjects requires includeCatalogs=true and an integer 1 to 20"
                ) from None
            raw_history = request.query_params.get("includeHistory", "false")
            if raw_history not in ("true", "false"):
                raise HTTPException(422, "includeHistory requires true or false")
            include_history = raw_history == "true"
            history_cursor = request.query_params.get("historyCursor")
            try:
                from gflow_cli.api.native_history import validate_project_history_options

                history_pages = (
                    int(request.query_params["historyMaxPages"])
                    if "historyMaxPages" in request.query_params
                    else None
                )
                history_media = (
                    int(request.query_params["historyMaxMedia"])
                    if "historyMaxMedia" in request.query_params
                    else None
                )
                validate_project_history_options(
                    include_history, history_cursor, history_pages, history_media
                )
            except ValueError:
                raise HTTPException(422, "Invalid native history controls") from None
            controls: dict[str, Any] = {}
            if include_history:
                controls.update(
                    {
                        "include_history": True,
                        "history_cursor": history_cursor,
                        "history_max_pages": history_pages,
                        "history_max_media": history_media,
                    }
                )
            if all_pages:
                controls.update({"all_pages": True, "max_pages": max_pages})
            if include_catalogs:
                controls.update({"include_catalogs": True, "max_projects": max_projects})
            cursor = request.query_params.get("cursor")
            if cursor is not None and (not cursor or len(cursor) > 4096):
                raise HTTPException(422, "Native project cursor requires 1 to 4096 characters")
            raw_resume = request.query_params.get("catalogProjectIds")
            try:
                resume_ids = validate_project_catalog_resume(
                    include_catalogs,
                    raw_resume.split(",") if raw_resume is not None else None,
                    cursor,
                    all_pages,
                    max_pages,
                )
            except ValueError:
                raise HTTPException(422, "Invalid native catalog resume controls") from None
            if resume_ids is not None:
                controls["catalog_project_ids"] = resume_ids
            if "limit" in request.query_params:
                raise HTTPException(422, "Native project pages have a fixed size of 21")
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "projects-list",
                    profile,
                    json.dumps({"cursor": cursor, **controls}),
                ],
                240 if all_pages or include_catalogs or include_history else 90,
            )
            if code:
                raise HTTPException(502, "Google project catalog unavailable")
            result = parse_json_output(raw)
            if result.get("status") != "ok" or not isinstance(result.get("projects"), list):
                raise HTTPException(502, "Google project catalog unavailable")
            if include_catalogs and not isinstance(result.get("project_catalogs"), list):
                raise HTTPException(502, "Google project catalogs unavailable")
            if include_history and not isinstance(result.get("account_history"), dict):
                raise HTTPException(502, "Google account history unavailable")
            observed: dict[str, Any] = {}
            if include_catalogs:
                try:
                    observed = observations.merge_catalogs(
                        profile, cfg.accounts[profile]["email"], result["project_catalogs"]
                    )
                except ValueError:
                    raise HTTPException(502, "Observed catalog metadata is inconsistent") from None
            if include_history:
                try:
                    observed = observations.merge_history(
                        profile, cfg.accounts[profile]["email"], result["account_history"]
                    )
                except ValueError:
                    raise HTTPException(502, "Observed history metadata is inconsistent") from None
            return {
                **(
                    {"inventoryObservations": observed}
                    if include_history or include_catalogs
                    else {}
                ),
                **({"catalogResume": True} if result.get("catalog_resume") is True else {}),
                **(
                    {
                        "accountHistory": result["account_history"],
                    }
                    if include_history
                    else {}
                ),
                "projects": [
                    {
                        "projectId": row["project_id"],
                        "name": row["name"],
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in ("project_id", "name")
                        },
                    }
                    for row in result["projects"]
                ],
                "cursor": result.get("next_cursor"),
                "scope": result.get("scope", "native Google account project catalog"),
                "returnedCount": result.get("returned_count", len(result["projects"])),
                "pagesRead": result.get("pages_read", 1),
                "paginationExhausted": result.get(
                    "pagination_exhausted", result.get("next_cursor") is None
                ),
                "complete": None,
                **(
                    {
                        "projectCatalogs": [
                            {**row, "projectId": row["project_id"]}
                            for row in result["project_catalogs"]
                        ],
                        "catalogProjectsRead": result["catalog_projects_read"],
                        "catalogCounts": result["catalog_counts"],
                        "pendingProjectIds": result["pending_project_ids"],
                        "catalogsCapped": result["catalogs_capped"],
                    }
                    if include_catalogs
                    else {}
                ),
            }
        code, output = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.cli",
                "project",
                "list",
                "--profile",
                profile,
                "--json",
                "--limit",
                "10000",
            ],
            30,
        )
        if code:
            raise HTTPException(502, "Local project catalog unavailable")
        rows = parse_json_output(output).get("projects", [])
        return {**page_slice(request, rows, "projects"), "scope": "local gflow project catalog"}

    @app.get(prefix + "/assets/media/{email}")
    async def media(request: Request, email: str) -> dict[str, Any]:
        profile = pick_account(email, [])
        project = request.query_params.get("projectId")
        if project:
            project = uuid_value(project, "projectId")
        source = request.query_params.get("source", "google")
        if source not in ("local", "google"):
            raise HTTPException(422, "source requires local or google")
        if source == "google":
            project = project or cfg.accounts[profile]["project"]
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "media-list",
                    profile,
                    json.dumps({"project_id": project}),
                ],
                60,
            )
            if code:
                raise HTTPException(502, "Google media library unavailable")
            result = parse_json_output(raw)
            if result.get("status") != "ok":
                raise HTTPException(502, "Google media library unavailable")
            native_rows: list[dict[str, Any]] = [
                {
                    **row,
                    "mediaGenerationId": row["media_id"],
                    "projectId": row["project_id"],
                    "mediaType": {"image": "IMAGE", "video": "VIDEO"}.get(row.get("kind"), "OTHER"),
                    "likelyUpload": row.get("likely_upload") is True,
                    **({"createTime": row["created_time"]} if "created_time" in row else {}),
                }
                for row in result["media"]
            ]
            selected: dict[str, Any] = (
                page_slice(request, native_rows, "media")
                if any(key in request.query_params for key in ("limit", "cursor"))
                else {"media": native_rows, "cursor": None}
            )
            return {
                **selected,
                "projectId": project,
                "count": len(selected["media"]),
                "observedCount": len(native_rows),
                "likelyUploads": sum(1 for row in selected["media"] if row["likelyUpload"] is True),
                "complete": None,
                "scope": "google-project-library",
                "inventoryScope": "timeline and attached snapshot; completeness unknown",
            }
        rows = sorted(store.asset_list(profile), key=lambda row: row["id"])
        if project:
            rows = [row for row in rows if row["project"] == project]
        items = [
            {
                **(
                    {"localArtifactId": row["id"]}
                    if "_" in row["id"]
                    else {"mediaGenerationId": row["id"]}
                ),
                **({"projectId": row["project"]} if row["project"] else {}),
                "mimeType": row["mime"],
            }
            for row in rows
        ]
        return {**page_slice(request, items, "media"), "scope": "selfhost-managed assets"}

    @app.delete(prefix + "/assets/{email}", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def delete_assets(
        request: Request, email: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        check_unknown(
            payload,
            {
                "mediaGenerationIds",
                "projectId",
                "localOnly",
                "operation",
                "async",
                "replyUrl",
                "replyRef",
            },
        )
        profile = pick_account(email, [])
        if payload.get("localOnly") is not True:
            if payload.get("localOnly") not in (None, False):
                raise HTTPException(422, "localOnly must be a boolean")
            operation = payload.get("operation", "archive")
            if operation not in {"archive", "delete"}:
                raise HTTPException(422, "operation requires archive or delete")
            values = payload.get("mediaGenerationIds")
            if (
                not isinstance(values, list)
                or not values
                or (operation == "archive" and len(cast(list[Any], values)) > 100)
            ):
                raise HTTPException(422, "Remote archive requires 1 to 100 mediaGenerationIds")
            controls: dict[str, Any] = {
                "email": email,
                **({"projectId": payload["projectId"]} if "projectId" in payload else {}),
            }
            slots = {f"media_{index}": value for index, value in enumerate(cast(list[Any], values))}
            controls.update(slots)
            await translate_input_aliases(
                controls, dict.fromkeys(slots, "media"), confirmed_delete=operation == "delete"
            )
            project = uuid_value(
                controls.get("projectId", cfg.accounts[profile]["project"]), "projectId"
            )
            ids = [uuid_value(controls[field], "mediaGenerationIds") for field in slots]
            if operation == "delete":
                from gflow_cli.api.transports.native_media_delete import validate_delete

                try:
                    project, normalized = validate_delete(project, ids, True)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                ids = list(normalized)
            elif len(set(ids)) != len(ids):
                raise HTTPException(422, "mediaGenerationIds must be distinct")
            if any(store.asset_in_use(identifier) for identifier in ids):
                raise HTTPException(409, "Asset is referenced by an active job")
            payload["mediaGenerationIds"] = ids
            payload["projectId"] = project
            return await submit(request, "assets/" + operation, payload, profile)
        ids = payload.get("mediaGenerationIds")
        if "projectId" in payload:
            if ids is not None:
                raise HTTPException(422, "Choose mediaGenerationIds or projectId")
            project = uuid_value(payload["projectId"], "projectId")
            ids = [row["id"] for row in store.asset_list(profile) if row["project"] == project]
        if (
            not isinstance(ids, list)
            or len(cast(list[Any], ids)) > 100
            or not all(isinstance(value, str) for value in cast(list[Any], ids))
        ):
            raise HTTPException(422, "mediaGenerationIds requires up to 100 registered IDs")
        selected = list(dict.fromkeys(cast(list[str], ids)))
        for identifier in selected:
            try:
                row = store.asset_get(identifier)
            except KeyError:
                raise HTTPException(404, "Managed asset not found") from None
            if row["profile"] != profile:
                raise HTTPException(422, "Asset belongs to another account")
            if store.asset_in_use(identifier):
                raise HTTPException(409, "Asset is referenced by an accepted or running job")
            try:
                contained_file(row["path"], cfg.root)
            except ValueError:
                raise HTTPException(
                    409, "Asset bytes are missing or outside the managed root"
                ) from None
        for identifier in selected:
            path = store.asset_delete(identifier)
            if path:
                contained_file(path, cfg.root).unlink()
        return {"deleted": selected, "scope": "local-cache", "googleLibraryModified": False}

    @app.get(prefix + "/assets/{media_id}/download")
    async def download(media_id: str) -> FileResponse:
        try:
            row = store.asset_get(media_id)
            path = contained_file(row["path"], cfg.root)
        except (KeyError, ValueError):
            raise HTTPException(404, "Managed asset not found") from None
        return FileResponse(path, media_type=row["mime"], filename=path.name)

    def verified_alias_account(binding: NativeAlias | NativeResourceAlias) -> None:
        configured = cfg.accounts.get(binding.profile)
        row = next((row for row in store.accounts() if row["profile"] == binding.profile), None)
        if (
            store.resolve_profile_scope(binding.profile, binding.account) != binding.profile
            or configured is None
            or configured["email"] != binding.account
            or row is None
            or row["email"] != binding.account
            or row["enabled"] != 1
            or row["verified"] != 1
        ):
            raise HTTPException(
                403, "Composite alias account is not currently verified and enabled"
            )

    async def native_alias_metadata(profile: str, project: str, identifier: str) -> dict[str, Any]:
        code, output = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "asset-get",
                profile,
                json.dumps({"project_id": project, "media_id": identifier}),
            ],
            120,
        )
        try:
            result = parse_json_output(output)
        except ValueError:
            raise HTTPException(502, "Native alias verification is unavailable") from None
        if (
            code
            or result.get("status") != "ok"
            or result.get("mediaGenerationId") != identifier
            or result.get("projectId") != project
        ):
            raise HTTPException(502, "Native alias verification is unresolved")
        return result

    @app.post(prefix + "/assets/{email}/aliases", status_code=201, openapi_extra=FORM_REQUEST_BODY)
    async def register_native_alias(
        email: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any]:
        from gflow_cli.api.transports.native_asset_lookup import media_url

        check_unknown(payload, {"alias", "mediaGenerationId", "projectId", "kind"})
        value = payload.get("alias")
        if not isinstance(value, str):
            raise HTTPException(422, "Composite alias requires a supported image/video shape")
        try:
            kind, expected_media = alias_spec(value)
        except ValueError:
            raise HTTPException(
                422, "Composite alias requires a supported image/video shape"
            ) from None
        if payload.get("kind") != kind:
            raise HTTPException(422, "Composite alias kind does not match the supplied kind")
        identifier = uuid_value(payload.get("mediaGenerationId"), "mediaGenerationId")
        if identifier != expected_media:
            raise HTTPException(422, "Composite alias does not match the explicit media UUID")
        profile = pick_account(email, [])
        project = uuid_value(
            payload.get("projectId", cfg.accounts[profile]["project"]), "projectId"
        )
        binding = NativeAlias(payload["alias"], profile, email, project, identifier, kind)
        verified_alias_account(binding)
        existing = aliases.get(binding.alias)
        if existing is not None and existing != binding:
            raise HTTPException(409, "Composite alias conflicts with its existing binding")
        result = await native_alias_metadata(profile, project, identifier)
        if result.get("kind") != kind:
            raise HTTPException(400, "Native media type does not match the composite alias")
        try:
            media_url(result.get("url"), kind)
        except ValueError:
            raise HTTPException(502, "Native alias verification URL is unavailable") from None
        try:
            aliases.register(binding)
        except ValueError:
            raise HTTPException(
                409, "Composite alias conflicts with its existing binding"
            ) from None
        return {
            "alias": binding.alias,
            "mediaGenerationId": binding.alias,
            "nativeMediaGenerationId": identifier,
            "projectId": project,
            "kind": kind,
            "verified": True,
            "scope": "self-hosted exact mapping verified by fresh native read",
        }

    @app.delete(prefix + "/assets/{email}/aliases/{alias}")
    async def remove_native_alias(email: str, alias: str) -> dict[str, Any]:
        profile = pick_account(email, [])
        try:
            removed = aliases.remove(alias, profile, email)
        except ValueError:
            raise HTTPException(
                403, "Composite alias is invalid or belongs to another scope"
            ) from None
        if not removed:
            raise HTTPException(
                404,
                "Composite alias has no verified mapping; register the exact "
                "account/project/media binding. Opaque UseAPI identity is not decoded.",
            )
        return {
            "alias": alias,
            "removed": True,
            "googleMediaDeleted": False,
            "scope": "local-alias",
        }

    async def native_asset_read(request: Request, media_id: str) -> Any:
        from gflow_cli.api.transports.native_asset_lookup import media_url

        raw = request.query_params.get("raw")
        if raw is not None and raw not in ("true", "1"):
            raise HTTPException(400, "When supplied, raw must be true or 1")
        email = request.query_params.get("email")
        binding: NativeAlias | None = None
        if media_id.startswith("user:"):
            try:
                binding = aliases.get(media_id)
            except ValueError:
                raise HTTPException(400, "Composite alias shape is unsupported") from None
            if binding is None:
                raise HTTPException(
                    404,
                    "Composite alias has no verified mapping; register the exact "
                    "account/project/media binding. Opaque UseAPI identity is not decoded.",
                )
            verified_alias_account(binding)
            if email is not None and email != binding.account:
                raise HTTPException(403, "Composite alias belongs to another account")
            if (
                "projectId" in request.query_params
                and uuid_value(request.query_params["projectId"], "projectId") != binding.project_id
            ):
                raise HTTPException(403, "Composite alias belongs to another project")
            profile, project, identifier = binding.profile, binding.project_id, binding.media_id
        else:
            if not email:
                raise HTTPException(
                    422, "Native asset lookup requires an explicit configured account"
                )
            profile = pick_account(email, [])
            project = uuid_value(
                request.query_params.get("projectId", cfg.accounts[profile]["project"]), "projectId"
            )
            identifier = uuid_value(media_id, "mediaGenerationId")
        payload = {"project_id": project, "media_id": identifier}
        code, output = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "asset-get",
                profile,
                json.dumps(payload),
            ],
            120,
        )
        try:
            result = parse_json_output(output)
        except ValueError:
            raise HTTPException(
                502, "Native asset read worker returned no valid response"
            ) from None
        if (
            not code
            and result.get("status") == "ok"
            and result.get("mediaGenerationId") == identifier
            and result.get("projectId") == project
            and result.get("kind") == "audio"
        ):
            raise HTTPException(
                400,
                "Native audio detail is available through SDK/CLI/MCP; "
                "this asset route supports image/video",
            )
        if (
            code
            or result.get("status") != "ok"
            or result.get("mediaGenerationId") != identifier
            or result.get("projectId") != project
            or result.get("kind") not in ("image", "video")
            or (binding is not None and result.get("kind") != binding.kind)
        ):
            raise HTTPException(502, "Native asset is unresolved in the selected project")
        try:
            url = media_url(result.get("url"), result["kind"])
        except ValueError:
            raise HTTPException(502, "Native asset download URL is unavailable") from None
        if raw is None:
            return JSONResponse(
                {"url": url, "mediaGenerationId": media_id}, headers={"Cache-Control": "no-store"}
            )
        directory = cfg.root / "output" / ("native-download-" + uuid.uuid4().hex)
        successful = False
        try:
            code, output = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "asset-download",
                    profile,
                    json.dumps({**payload, "output_dir": str(directory)}),
                ],
                210,
            )
            try:
                downloaded = parse_json_output(output)
            except ValueError:
                raise HTTPException(
                    502, "Native media download worker returned no valid response"
                ) from None
            if (
                code
                or downloaded.get("status") != "ok"
                or downloaded.get("mediaGenerationId") != identifier
                or downloaded.get("projectId") != project
                or downloaded.get("kind") != result["kind"]
                or downloaded.get("mimeType")
                not in (
                    ("image/png", "image/jpeg") if result["kind"] == "image" else ("video/mp4",)
                )
            ):
                raise HTTPException(502, "Native media download validation failed")
            try:
                path = contained_file(downloaded["path"], directory)
            except (KeyError, ValueError):
                raise HTTPException(502, "Native media download path is unavailable") from None
            from gflow_cli.selfhost.native_asset_response import EphemeralFileResponse

            response = EphemeralFileResponse(path, directory, media_type=downloaded["mimeType"])
            successful = True
            return response
        finally:
            if not successful:
                import shutil

                shutil.rmtree(directory, ignore_errors=True)

    @app.get(prefix + "/assets/{media_id}")
    async def get_asset(request: Request, media_id: str) -> Any:
        source = request.query_params.get(
            "source", "google" if media_id.startswith("user:") else "local"
        )
        if source not in ("local", "google"):
            raise HTTPException(422, "Asset source requires local or google")
        if source == "google":
            return await native_asset_read(request, media_id)
        if set(request.query_params) - {"source", "raw"}:
            raise HTTPException(
                422, "Local asset lookup does not accept native account/project controls"
            )
        raw = request.query_params.get("raw", "false")
        if raw not in ("true", "false", "1", "0"):
            raise HTTPException(422, "raw must be true or false")
        if raw in ("true", "1"):
            return await download(media_id)
        try:
            row = store.asset_get(media_id)
        except KeyError:
            raise HTTPException(404, "Managed asset not found") from None
        return {
            **(
                {"localArtifactId": row["id"]}
                if "_" in row["id"]
                else {"mediaGenerationId": row["id"]}
            ),
            **({"projectId": row["project"]} if row["project"] else {}),
            "mimeType": row["mime"],
            "downloadPath": f"{prefix}/assets/{row['id']}/download",
        }

    def preset_voices(request: Request) -> list[dict[str, Any]]:
        if request.query_params.get("source", "system") != "system":
            feature_missing("custom voices")
        if request.query_params.get("email"):
            pick_account(request.query_params["email"], [])
        from gflow_cli.api.character import VOICES

        return [
            {
                "ref": voice.name,
                "name": voice.name,
                "voice": voice.name,
                "displayName": voice.name,
                "description": voice.description,
                "sampleUrl": voice.sample_url,
                "source": "system",
            }
            for voice in VOICES
        ]

    async def native_catalog(
        request: Request,
        verb: str,
        key: str,
        controls: dict[str, Any] | None = None,
        *,
        selection: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        if selection is None:
            profile = pick_account(request.query_params.get("email"), [])
            project = uuid_value(
                request.query_params.get("projectId", cfg.accounts[profile]["project"]), "projectId"
            )
        else:
            profile, project = selection
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                verb,
                profile,
                json.dumps({"project_id": project, **(controls or {})}),
            ],
            60,
        )
        if code:
            raise HTTPException(502, "Google native catalog unavailable")
        result = parse_json_output(raw)
        if result.get("status") != "ok" or not isinstance(result.get(key), list):
            raise HTTPException(502, "Google native catalog unavailable")
        return {key: result[key], "projectId": project, "scope": "native Google project catalog"}

    def character_item(row: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
        item = {
            "ref": row["entity_id"],
            "projectId": row["project_id"],
            "displayName": row["display_name"],
            "workflowIds": row["workflow_ids"],
        }
        if row.get("thumbnail_media_id"):
            item["thumbnailMediaId"] = row["thumbnail_media_id"]
        if detail:
            item["personalityNotes"] = row.get("personality") or ""
        if row.get("voice"):
            item["voice"] = row["voice"]
        return item

    def character_project(controls: dict[str, Any]) -> tuple[str, str]:
        if len(cfg.accounts) > 1 and not controls.get("email"):
            raise HTTPException(422, "Native character operations require an explicit account")
        profile = pick_account(controls.get("email"), [])
        project = uuid_value(
            controls.get("projectId", cfg.accounts[profile]["project"]), "projectId"
        )
        return profile, project

    def character_fields(payload: dict[str, Any]) -> None:
        name = payload.get("displayName")
        if "displayName" in payload and (
            not isinstance(name, str) or not 1 <= len(name) <= 200 or not name.strip()
        ):
            raise HTTPException(422, "displayName requires 1 to 200 characters")
        if "voice" in payload:
            from gflow_cli.api.transports.migrated_characters import normalize_voice

            try:
                payload["voice"] = normalize_voice(payload["voice"])
            except ValueError:
                raise HTTPException(
                    422,
                    "voice requires a known system preset or owned saved voice UUID; "
                    "clearing is unverified",
                ) from None
        notes = payload.get("personalityNotes")
        if "personalityNotes" in payload and (not isinstance(notes, str) or len(notes) > 2000):
            raise HTTPException(422, "personalityNotes requires at most 2000 characters")

    async def character_mutation(profile: str, verb: str, data: dict[str, Any]) -> dict[str, Any]:
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                verb,
                profile,
                json.dumps(data),
            ],
            180,
        )
        if code:
            raise HTTPException(
                502, "Native character outcome unconfirmed; inspect Flow before retrying"
            )
        result = parse_json_output(raw)
        if result.get("status") != "ok":
            detail: dict[str, Any] = {
                "code": "native_character_outcome_unknown",
                "detail": "Inspect Flow before retrying; no automatic retry occurred",
            }
            partial_code = result.get("code")
            if (
                partial_code
                in (
                    "character_binding_outcome_unknown",
                    "character_delete_outcome_unknown",
                    "character_update_outcome_unknown",
                )
                and result.get("project_id") == data["project_id"]
            ):
                identity_key = (
                    "createdCharacterRef"
                    if partial_code == "character_binding_outcome_unknown"
                    else "characterRef"
                )
                reference = result.get(identity_key)
                try:
                    validated_ref = (
                        str(uuid.UUID(reference)) if isinstance(reference, str) else None
                    )
                except ValueError:
                    validated_ref = None
                if validated_ref and (
                    identity_key == "createdCharacterRef" or validated_ref == data.get("entity_id")
                ):
                    detail.update(code=partial_code, projectId=data["project_id"])
                    detail[identity_key] = validated_ref
            if (
                partial_code == "character_create_outcome_unknown"
                and result.get("project_id") == data["project_id"]
            ):
                detail.update(code=partial_code, projectId=data["project_id"])
            raise HTTPException(502, detail)
        if verb == "character-delete":
            return {"deleted": result["deleted"], "scope": "native Google project character"}
        return {
            "character": character_item(result["character"], detail=True),
            "scope": "native Google project character",
        }

    @app.post(prefix + "/characters", openapi_extra=FORM_REQUEST_BODY)
    async def create_character(
        payload: Annotated[dict[str, Any], Depends(parse_payload)],
    ) -> dict[str, Any]:
        check_unknown(
            payload,
            {
                "email",
                "projectId",
                "displayName",
                "imageReference_1",
                "imageReference_2",
                "personalityNotes",
                "voice",
            },
        )
        translated = await translate_input_aliases(
            payload, {"imageReference_1": "image", "imageReference_2": "image", "voice": "voice"}
        )
        character_fields(payload)
        if "displayName" not in payload:
            raise HTTPException(422, "displayName is required")
        await cache_alias_images(
            payload,
            [value for field, value in translated.items() if field.startswith("imageReference_")],
        )
        media_ids = [uuid_value(payload.get("imageReference_1"), "imageReference_1")]
        if "imageReference_2" in payload:
            media_ids.append(uuid_value(payload["imageReference_2"], "imageReference_2"))
        try:
            assets = [store.asset_get(identifier) for identifier in media_ids]
        except KeyError:
            raise HTTPException(
                422, "Every character reference must be a registered native image"
            ) from None
        profile = pick_account(payload.get("email"), media_ids)
        project = uuid_value(payload.get("projectId", assets[0]["project"]), "projectId")
        if any(
            asset["project"] != project or asset["mime"] not in ("image/png", "image/jpeg")
            for asset in assets
        ):
            raise HTTPException(
                422, "Every character reference must be an image in the selected project"
            )
        from PIL import Image

        def verify_images() -> None:
            for asset in assets:
                image_path = contained_file(asset["path"], cfg.root)
                if image_path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError("Image exceeds limit")
                with Image.open(image_path) as image:
                    if image.format not in ("PNG", "JPEG"):
                        raise ValueError("Unsupported character image")
                    image.verify()

        try:
            await run_in_threadpool(verify_images)
        except (ValueError, OSError, Image.DecompressionBombError):
            raise HTTPException(
                422, "Registered character image bytes are unavailable or invalid"
            ) from None
        return await character_mutation(
            profile,
            "character-create",
            {
                "project_id": project,
                "display_name": payload["displayName"],
                "media_id": media_ids[0],
                **({"second_media_id": media_ids[1]} if len(media_ids) > 1 else {}),
                "image_reference_confirmed": True,
                **({"voice": payload["voice"]} if "voice" in payload else {}),
                **(
                    {"personality": payload["personalityNotes"]}
                    if "personalityNotes" in payload
                    else {}
                ),
            },
        )

    @app.patch(prefix + "/characters/{ref}", openapi_extra=FORM_REQUEST_BODY)
    async def patch_character(
        ref: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any]:
        check_unknown(payload, {"email", "projectId", "displayName", "personalityNotes", "voice"})
        character_fields(payload)
        if not ({"displayName", "personalityNotes", "voice"} & payload.keys()):
            raise HTTPException(422, "At least one character metadata field is required")
        profile, project = character_project(payload)
        return await character_mutation(
            profile,
            "character-update",
            {
                "project_id": project,
                "entity_id": uuid_value(ref, "ref"),
                **({"display_name": payload["displayName"]} if "displayName" in payload else {}),
                **({"voice": payload["voice"]} if "voice" in payload else {}),
                **(
                    {"personality": payload["personalityNotes"]}
                    if "personalityNotes" in payload
                    else {}
                ),
            },
        )

    @app.delete(prefix + "/characters/{ref}")
    async def delete_character(request: Request, ref: str) -> dict[str, Any]:
        controls = {**dict(request.query_params), "ref": ref}
        await translate_input_aliases(controls, {"ref": "character"})
        profile, project = character_project(controls)
        return await character_mutation(
            profile,
            "character-delete",
            {
                "project_id": project,
                "entity_id": uuid_value(controls["ref"], "ref"),
            },
        )

    def resource_alias_scope(request: Request, alias: str, kind: str) -> NativeResourceAlias:
        try:
            binding = resource_aliases.get(alias)
        except ValueError:
            raise HTTPException(400, "Unsupported resource composite alias") from None
        if binding is None:
            raise HTTPException(404, "Resource composite alias is not registered")
        if binding.kind != kind:
            raise HTTPException(400, "Resource composite alias has another kind")
        verified_alias_account(binding)
        account = request.query_params.get("email")
        if account is not None and account != binding.account:
            raise HTTPException(403, "Resource composite alias belongs to another account")
        if (
            "projectId" in request.query_params
            and uuid_value(request.query_params["projectId"], "projectId") != binding.project_id
        ):
            raise HTTPException(403, "Resource composite alias belongs to another project")
        return binding

    def verify_resource_declarations(
        binding: NativeResourceAlias, row: dict[str, Any], *, registration: bool
    ) -> None:
        mismatch = 400 if registration else 502
        audio: dict[str, Any]
        if binding.kind == "voice":
            if row.get("project_id") != binding.project_id or row.get("ref") != binding.native_id:
                raise HTTPException(502, "Saved voice alias ownership is unresolved")
            if row.get("workflow_id") != binding.workflow_id:
                raise HTTPException(mismatch, "Saved voice workflow does not match its alias")
            audio = row
        else:
            if (
                row.get("project_id") != binding.project_id
                or row.get("entity_id") != binding.native_id
            ):
                raise HTTPException(502, "Character alias ownership is unresolved")
            images = row.get("image_references")
            if not isinstance(images, list):
                raise HTTPException(502, "Character alias image details are unavailable")
            images = cast(list[Any], images)
            if len(images) != binding.image_count:
                raise HTTPException(mismatch, "Character image count does not match its alias")
            identifiers: set[str] = set()
            for candidate in images:
                if not isinstance(candidate, dict):
                    raise HTTPException(502, "Character alias image ownership is unresolved")
                image = cast(dict[str, Any], candidate)
                identifier = uuid_value(image.get("media_id"), "native image identity")
                uuid_value(image.get("workflow_id"), "native workflow identity")
                if identifier in identifiers:
                    raise HTTPException(502, "Character alias image identity is ambiguous")
                identifiers.add(identifier)
            if binding.voice_workflow_id is None:
                return
            raw_audio = row.get("voice_detail")
            if not isinstance(raw_audio, dict):
                raise HTTPException(mismatch, "Character alias requires an owned saved voice")
            audio = cast(dict[str, Any], raw_audio)
            if audio.get("source") != "user":
                raise HTTPException(mismatch, "Character alias requires an owned saved voice")
            if audio.get("project_id") != binding.project_id:
                raise HTTPException(502, "Character saved voice project is unresolved")
            if audio.get("workflow_id") != binding.voice_workflow_id:
                raise HTTPException(
                    mismatch, "Character saved voice workflow does not match its alias"
                )
            uuid_value(audio.get("ref"), "native saved voice identity")
            if audio.get("voice") != audio.get("ref"):
                raise HTTPException(502, "Character saved voice identity is unresolved")
        # Typed saved-voice detail omits the catalogue-only source discriminator.
        if audio.get("deleted") is True or audio.get("source", "user") != "user":
            raise HTTPException(502, "Saved voice playback is unavailable")
        value = audio.get("audio_url")
        if not isinstance(value, str) or len(value) > 8192:
            raise HTTPException(502, "Saved voice playback is unavailable")
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise HTTPException(502, "Saved voice playback is unavailable") from None
        if (
            parsed.scheme != "https"
            or parsed.netloc != "flow-content.google"
            or not parsed.path.startswith("/audio/")
            or parsed.fragment
        ):
            raise HTTPException(502, "Saved voice playback is unavailable")

    async def resource_alias_metadata(binding: NativeResourceAlias) -> dict[str, Any]:
        character = binding.kind == "character"
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "character-detail" if character else "voice-saved-get",
                binding.profile,
                json.dumps(
                    {
                        "project_id": binding.project_id,
                        "entity_id" if character else "ref": binding.native_id,
                    }
                ),
            ],
            120,
        )
        try:
            result = parse_json_output(raw)
            row = result["character"] if character else result
            if code or result.get("status") != "ok" or not isinstance(row, dict):
                raise ValueError
            if result.get("project_id") != binding.project_id:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise HTTPException(502, "Fresh resource alias detail is unavailable") from None
        return cast(dict[str, Any], row)

    @app.post(
        prefix + "/characters/{email}/aliases", status_code=201, openapi_extra=FORM_REQUEST_BODY
    )
    @app.post(prefix + "/voices/{email}/aliases", status_code=201, openapi_extra=FORM_REQUEST_BODY)
    async def register_resource_alias(
        request: Request, email: str, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any]:
        character = request.url.path.split("/")[3] == "characters"
        check_unknown(
            payload,
            {"alias", "projectId", "entityId"}
            if character
            else {"alias", "projectId", "mediaId", "workflowId"},
        )
        alias = payload.get("alias")
        if not isinstance(alias, str):
            raise HTTPException(422, "Resource composite alias requires a supported shape")
        try:
            spec = resource_alias_spec(alias)
        except ValueError:
            raise HTTPException(
                422, "Resource composite alias requires a supported shape"
            ) from None
        if (spec.kind == "character") != character:
            raise HTTPException(422, "Resource alias kind does not match the endpoint")
        native = uuid_value(payload.get("entityId" if character else "mediaId"), "native identity")
        if native != spec.native_id:
            raise HTTPException(422, "Resource alias does not match its explicit native identity")
        if (
            not character
            and uuid_value(payload.get("workflowId"), "workflowId") != spec.workflow_id
        ):
            raise HTTPException(422, "Voice alias does not match its explicit workflow identity")
        profile = pick_account(email, [])
        project = uuid_value(
            payload.get("projectId", cfg.accounts[profile]["project"]), "projectId"
        )
        binding = NativeResourceAlias(
            alias,
            profile,
            cfg.accounts[profile]["email"],
            project,
            spec.kind,
            native,
            workflow_id=spec.workflow_id,
            image_count=spec.image_count,
            voice_workflow_id=spec.voice_workflow_id,
        )
        verified_alias_account(binding)
        existing = resource_aliases.get(alias)
        if existing is not None and existing != binding:
            raise HTTPException(409, "Resource composite alias conflicts with its existing binding")
        row = await resource_alias_metadata(binding)
        verify_resource_declarations(binding, row, registration=True)
        try:
            resource_aliases.register(binding)
        except ValueError:
            raise HTTPException(
                409, "Resource composite alias conflicts with its existing binding"
            ) from None
        return {
            "alias": alias,
            "ref": alias,
            "nativeRef": native,
            "projectId": project,
            "kind": spec.kind,
            "verified": True,
            "scope": "exact local mapping verified by fresh native resource detail",
        }

    @app.delete(prefix + "/characters/{email}/aliases/{alias}")
    @app.delete(prefix + "/voices/{email}/aliases/{alias}")
    async def remove_resource_alias(request: Request, email: str, alias: str) -> dict[str, Any]:
        if request.query_params:
            raise HTTPException(422, "Local alias removal accepts no query controls")
        profile = pick_account(email, [])
        try:
            spec = resource_alias_spec(alias)
            if (spec.kind == "character") != (request.url.path.split("/")[3] == "characters"):
                raise ValueError
            removed = resource_aliases.remove(alias, profile, cfg.accounts[profile]["email"])
        except ValueError:
            raise HTTPException(
                403, "Resource alias is invalid or belongs to another scope"
            ) from None
        if not removed:
            raise HTTPException(404, "Resource composite alias is not registered")
        return {
            "alias": alias,
            "removed": True,
            "googleResourceDeleted": False,
            "scope": "local-alias",
        }

    @app.get(prefix + "/characters/{ref}")
    async def get_character(request: Request, ref: str) -> JSONResponse:
        if request.query_params.get("source", "google") != "google":
            raise HTTPException(422, "Character source requires google")
        if "catalog" in request.query_params:
            raise HTTPException(422, "catalog is a voice-only option")
        binding = (
            resource_alias_scope(request, ref, "character") if ref.startswith("user:") else None
        )
        if binding is None:
            profile, project = character_project(dict(request.query_params))
            ref = uuid_value(ref, "ref")
        else:
            profile, project, ref = binding.profile, binding.project_id, binding.native_id
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "character-detail",
                profile,
                json.dumps({"project_id": project, "entity_id": ref}),
            ],
            100,
        )
        if code:
            raise HTTPException(502, "Native character detail unresolved")
        try:
            result = parse_json_output(raw)
            row = result["character"]
            if (
                result.get("status") != "ok"
                or row["entity_id"] != ref
                or row["project_id"] != project
            ):
                raise ValueError
            if binding is not None:
                verify_resource_declarations(binding, row, registration=False)
            item = character_item(row, detail=True)
            item["entityId"] = ref
            item["imageReferences"] = [
                {
                    "workflowId": image["workflow_id"],
                    "mediaId": image["media_id"],
                    "previewUrl": image["preview_url"],
                }
                for image in row.get("image_references", [])
            ]
            if row.get("thumbnail_url"):
                item["thumbnailUrl"] = row["thumbnail_url"]
            voice = row.get("voice_detail")
            if voice:
                item["voice"] = {
                    "source": voice["source"],
                    "voice": voice["voice"],
                    "displayName": voice.get("display_name", ""),
                }
                for original, public in (
                    ("workflow_id", "workflowId"),
                    ("ref", "mediaId"),
                    ("audio_url", "audioUrl"),
                    ("dialogue", "dialog"),
                    ("performance", "voicePerformance"),
                    ("preset_voice", "baseVoice"),
                ):
                    if original in voice:
                        item["voice"][public] = voice[original]
        except (KeyError, TypeError, ValueError):
            raise HTTPException(502, "Native character detail unresolved") from None
        if binding is not None:
            item["ref"] = binding.alias
            item["nativeRef"] = ref
        return JSONResponse(item, headers={"Cache-Control": "no-store"})

    @app.get(prefix + "/characters")
    async def characters(request: Request) -> dict[str, Any]:
        if request.query_params.get("source", "google") != "google":
            raise HTTPException(422, "Character source requires google")
        result = await native_catalog(request, "characters-list", "characters")
        result["characters"] = [character_item(row) for row in result["characters"]]
        return result

    def video_audio_value(value: object) -> str:
        from gflow_cli.api.native_video_audio import normalize_audio_reference
        from gflow_cli.errors import ConfigurationError

        try:
            return normalize_audio_reference(value)
        except ConfigurationError:
            raise HTTPException(
                422, "Audio reference requires a UUID or recognized system preset"
            ) from None

    def saved_voice_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "ref": row["ref"],
            "voice": row["ref"],
            "mediaId": row["ref"],
            "projectId": row["project_id"],
            "workflowId": row["workflow_id"],
            "displayName": row["display_name"],
            "source": "user",
            **({"audioUrl": row["audio_url"]} if row.get("audio_url") else {}),
            **({"baseVoice": row["preset_voice"]} if row.get("preset_voice") else {}),
            **({"dialog": row["dialogue"]} if row.get("dialogue") else {}),
            **({"voicePerformance": row["performance"]} if row.get("performance") else {}),
            **({"description": row["description"]} if row.get("description") else {}),
        }

    @app.post(prefix + "/voices", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def create_voice(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        check_unknown(
            payload,
            {
                "captchaToken",
                "captchaOrder",
                "captchaRetry",
                "email",
                "projectId",
                "displayName",
                "voice",
                "dialog",
                "performance",
                "voicePerformance",
                "async",
                "replyRef",
                "replyUrl",
            },
        )
        profile, project = character_project(payload)
        from gflow_cli.api.character import VOICE_NAMES

        if payload.get("voice") not in VOICE_NAMES:
            raise HTTPException(422, "voice must be a case-sensitive canonical system preset")
        if "voicePerformance" in payload and "performance" in payload:
            raise HTTPException(422, "Choose voicePerformance or performance")
        payload["performance"] = payload.pop("voicePerformance", payload.get("performance", ""))
        from gflow_cli.api.transports.native_voices import preview_payload

        try:
            preview_payload(
                project,
                preset=payload.get("voice", ""),
                dialogue=payload.get("dialog", ""),
                performance=payload.get("performance", ""),
                display_name=payload.get("displayName", ""),
                captcha_token="validation-only",
            )
        except (ValueError, TypeError):
            raise HTTPException(
                422,
                "Voice requires a known preset, displayName 1..200, "
                "dialog and performance 1..120 characters",
            ) from None
        return await submit(request, "voices/create", payload, profile)

    @app.delete(prefix + "/voices/{ref}", response_model=None)
    async def delete_voice(request: Request, ref: str) -> dict[str, Any] | JSONResponse:
        payload: dict[str, Any] = dict(request.query_params)
        check_unknown(payload, {"email", "projectId", "async", "replyRef", "replyUrl", "source"})
        if payload.pop("source", "user") not in {"custom", "user"}:
            raise HTTPException(422, "Only a saved custom voice can be deleted")
        asynchronous = payload.pop("async", "false")
        if asynchronous not in ("true", "false"):
            raise HTTPException(422, "async must be true or false")
        payload["async"] = asynchronous == "true"
        payload["ref"] = ref
        await translate_input_aliases(payload, {"ref": "voice"})
        profile, project = character_project(payload)
        payload["projectId"], payload["ref"] = project, uuid_value(payload["ref"], "ref")
        return await submit(request, "voices/delete", payload, profile)

    def system_voice_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "ref": row["voice"],
            "name": row["voice"],
            "voice": row["voice"],
            "displayName": row["voice"],
            "description": row["description"],
            "source": "system",
            **({"sampleUrl": row["sample_url"]} if row.get("sample_url") else {}),
        }

    def saved_voice_list_item(row: dict[str, Any]) -> dict[str, Any]:
        item = saved_voice_item(row)
        item.pop("audioUrl", None)
        return item

    @app.get(prefix + "/voices")
    async def voices(request: Request) -> dict[str, Any]:
        combined = (
            request.url.path == prefix + "/voices"
            and "source" not in request.query_params
            and "catalog" not in request.query_params
        )
        if combined:
            if not request.query_params.get("email"):
                raise HTTPException(422, "Combined voice inventory requires email")
            profile = pick_account(request.query_params["email"], [])
            configured = cfg.accounts[profile].copy()
            project = uuid_value(
                request.query_params.get("projectId", configured["project"]), "projectId"
            )
            selection = (profile, project)
            system = await native_catalog(request, "voice-presets", "voices", selection=selection)
            saved = await native_catalog(request, "voice-saved-list", "voices", selection=selection)
            current = store.account_lookup(configured["email"])
            if (
                cfg.accounts.get(profile) != configured
                or current is None
                or current["profile"] != profile
                or current["project"] != configured["project"]
                or current["enabled"] != 1
                or current["verified"] != 1
            ):
                raise HTTPException(409, "Voice inventory account changed during the read")
            if any(row.get("project_id") != project for row in saved["voices"]):
                raise HTTPException(502, "Saved voice inventory project scope is unresolved")
            return {
                "voices": [system_voice_item(row) for row in system["voices"]]
                + [saved_voice_list_item(row) for row in saved["voices"]],
                "projectId": system["projectId"],
                "scope": "native Google project system and saved-user voice catalog",
                "complete": None,
            }
        source = request.query_params.get("source", "system")
        if source in {"custom", "user"}:
            result = await native_catalog(request, "voice-saved-list", "voices")
            result["voices"] = [saved_voice_list_item(row) for row in result["voices"]]
            return result
        if source != "system":
            raise HTTPException(422, "Voice source requires system or user")
        catalog = request.query_params.get("catalog", "bundled")
        if catalog not in ("bundled", "google"):
            raise HTTPException(422, "Voice catalog requires bundled or google")
        if catalog == "google":
            result = await native_catalog(request, "voice-presets", "voices")
            result["voices"] = [system_voice_item(row) for row in result["voices"]]
            return result
        if "projectId" in request.query_params:
            raise HTTPException(422, "projectId requires catalog=google")
        return {"voices": preset_voices(request), "scope": "bundled system voice catalog"}

    @app.get(prefix + "/voices/{ref}", response_model=None)
    async def voice(request: Request, ref: str) -> dict[str, Any] | JSONResponse:
        binding = resource_alias_scope(request, ref, "voice") if ref.startswith("user:") else None
        source = request.query_params.get("source", "user" if binding is not None else "system")
        if binding is not None and source not in {"custom", "user"}:
            raise HTTPException(422, "Saved voice alias source requires user or custom")
        if source in {"custom", "user"}:
            if binding is None:
                profile, project = character_project(dict(request.query_params))
            else:
                profile, project, ref = binding.profile, binding.project_id, binding.native_id
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "voice-saved-get",
                    profile,
                    json.dumps({"project_id": project, "ref": uuid_value(ref, "ref")}),
                ],
                60,
            )
            if code:
                raise HTTPException(502, "Saved voice detail unavailable")
            result = parse_json_output(raw)
            if result.get("status") != "ok":
                raise HTTPException(502, "Saved voice detail unavailable")
            if result.get("project_id") != project or result.get("ref") != uuid_value(ref, "ref"):
                raise HTTPException(502, "Saved voice detail ownership unresolved")
            if binding is not None:
                verify_resource_declarations(binding, result, registration=False)
            item = saved_voice_item(result)
            if binding is not None:
                item["ref"] = item["voice"] = binding.alias
                item["nativeRef"] = ref
            return JSONResponse(item, headers={"Cache-Control": "no-store"})
        match = next(
            (
                item
                for item in (await voices(request))["voices"]
                if item["ref"].casefold() == ref.casefold()
            ),
            None,
        )
        if match is None:
            raise HTTPException(404, "System voice not found")
        return match

    @app.get(prefix + "/images/upscale/capabilities")
    async def image_upscale_capabilities(request: Request) -> JSONResponse:
        """Fresh per-image menu observation; synchronous, URL-free and never queued."""
        from gflow_cli.api.transports.migrated_upscale import validate_upscale_capabilities

        profile = pick_account(request.query_params.get("email"), [])
        project = uuid_value(
            request.query_params.get("projectId", cfg.accounts[profile]["project"]), "projectId"
        )
        media = uuid_value(request.query_params.get("mediaGenerationId"), "mediaGenerationId")
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                "image-upscale-capabilities",
                profile,
                json.dumps({"project_id": project, "media_id": media}),
            ],
            60,
        )
        if code:
            raise HTTPException(502, "Image capability ownership/read verification unavailable")
        try:
            result = parse_json_output(raw)
            if result.get("status") != "ok":
                raise ValueError("Image capability read failed")
            observed = validate_upscale_capabilities(result, project=project, media=media)
        except ValueError:
            raise HTTPException(502, "Image capability observation unavailable") from None
        return JSONResponse(
            {
                "projectId": project,
                "mediaGenerationId": media,
                "capabilities": observed["capabilities"],
                "scope": observed["scope"],
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get(prefix + "/images/reference/models")
    async def image_reference_models(request: Request) -> dict[str, Any]:
        return await native_catalog(request, "image-reference-models", "models")

    @app.get(prefix + "/videos/upscale/models")
    async def promotion_models(request: Request) -> dict[str, Any]:
        resolution = request.query_params.get("resolution", "1080p")
        if resolution not in {"720p", "1080p", "4k"}:
            raise HTTPException(422, "Native promotion target must be720p,1080p or4k")
        return await native_catalog(
            request, "promotion-models", "models", {"resolution": resolution}
        )

    @app.get(prefix + "/videos/extend/models")
    async def extension_models(request: Request) -> dict[str, Any]:
        return await native_catalog(request, "extension-models", "models")

    @app.get(prefix + "/videos/reference/models")
    async def reference_models(request: Request) -> dict[str, Any]:
        with_audio = request.query_params.get("withAudio", "false")
        if with_audio not in {"true", "false"}:
            raise HTTPException(422, "withAudio must be true or false")
        return await native_catalog(
            request, "reference-models", "models", {"with_audio": with_audio == "true"}
        )

    @app.get(prefix + "/videos/edit/models")
    async def edit_models(request: Request) -> dict[str, Any]:
        return await native_catalog(request, "edit-models", "models")

    @app.post(prefix + "/videos/extend", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def extend_video(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        if not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        check_unknown(
            payload,
            {
                "captchaToken",
                "captchaOrder",
                "captchaRetry",
                "email",
                "projectId",
                "mediaGenerationId",
                "prompt",
                "model",
                "modelKey",
                "count",
                "aspectRatio",
                "trimStartFrame",
                "trimEndFrame",
                "async",
                "replyRef",
                "replyUrl",
            },
        )
        native_video_controls(payload)
        if "model" in payload and "modelKey" in payload:
            raise HTTPException(422, "Choose model or modelKey for extension")
        if "modelKey" not in payload:
            model = payload.setdefault("model", "veo-3.1-fast")
            if not isinstance(model, str) or model not in VIDEO_ALIASES or model == "omni-flash":
                raise HTTPException(422, "Extension requires a supported Veo model")
        await translate_input_aliases(payload, {"mediaGenerationId": "video"})
        profile, project = character_project(payload)
        payload["mediaGenerationId"] = uuid_value(
            payload.get("mediaGenerationId"), "mediaGenerationId"
        )
        from gflow_cli.api.native_extension import extension_args, new_extension_started
        from gflow_cli.errors import GFlowError

        # Validate the same exact source codec before accepting a durable job.
        try:
            count = payload.setdefault("count", 1)
            if type(count) is not int or not 1 <= count <= 4:
                raise ValueError("count")
            extension_args(
                new_extension_started(project, payload["mediaGenerationId"], count),
                prompt=payload.get("prompt", ""),
                model_key=payload.get("modelKey") or "validation-native-model",
                aspect=payload.get("aspectRatio") or "16:9",
                token="validation-only",
                trim_start_frame=payload.get("trimStartFrame"),
                trim_end_frame=payload.get("trimEndFrame"),
            )
        except (ValueError, TypeError, GFlowError):
            raise HTTPException(
                422,
                "Extension requires source UUID, prompt, optional native "
                "modelKey, count 1..4 and valid optional aspect/frame trims",
            ) from None
        return await submit(request, "videos/extend", payload, profile)

    async def native_reference_video(
        request: Request, payload: dict[str, Any]
    ) -> dict[str, Any] | JSONResponse:
        if not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        allowed = {
            "captchaToken",
            "captchaOrder",
            "captchaRetry",
            "email",
            "projectId",
            "prompt",
            "model",
            "modelKey",
            "count",
            "aspectRatio",
            "duration",
            "resolution",
            "async",
            "replyRef",
            "replyUrl",
        }
        allowed.update(f"referenceImage_{i}" for i in range(1, 8))
        allowed.update(f"referenceAudio_{i}" for i in range(1, 6))
        allowed.update(f"character_{i}" for i in range(1, 8))
        check_unknown(payload, allowed)
        if payload.get("model", "omni-flash") != "omni-flash":
            raise HTTPException(422, "Audio ingredients currently require Omni Flash")
        native_video_controls(payload)
        await translate_input_aliases(
            payload,
            {
                **{f"referenceImage_{i}": "image-or-character" for i in range(1, 8)},
                **{f"referenceAudio_{i}": "voice" for i in range(1, 6)},
                **{f"character_{i}": "character" for i in range(1, 8)},
            },
        )
        profile, project = character_project(payload)
        images = [
            uuid_value(payload[f"referenceImage_{i}"], f"referenceImage_{i}")
            for i in range(1, 8)
            if f"referenceImage_{i}" in payload
        ]
        audio = [
            video_audio_value(payload[f"referenceAudio_{i}"])
            for i in range(1, 6)
            if f"referenceAudio_{i}" in payload
        ]
        characters = [
            uuid_value(payload[f"character_{i}"], f"character_{i}")
            for i in range(1, 8)
            if f"character_{i}" in payload
        ]
        slot_ids = {
            key: video_audio_value(payload[key])
            if key.startswith("referenceAudio_")
            else uuid_value(payload[key], key)
            for family, cap in (("referenceImage", 7), ("referenceAudio", 5), ("character", 7))
            for i in range(1, cap + 1)
            if (key := f"{family}_{i}") in payload
        }
        from gflow_cli.api.reference_markers import ReferenceSlot

        slots = {
            key: ReferenceSlot(
                "audio"
                if key.startswith("referenceAudio_")
                else "character"
                if key.startswith("character_")
                else "image",
                value,
            )
            for key, value in slot_ids.items()
        }
        from gflow_cli.api.native_reference_video import new_reference_started, reference_args
        from gflow_cli.errors import GFlowError

        try:
            reference_args(
                new_reference_started(project, payload.setdefault("count", 1)),
                prompt=payload.get("prompt", ""),
                image_ids=tuple(images),
                audio_ids=tuple(audio),
                character_ids=tuple(characters),
                reference_slots=slots,
                model_key=payload.get("modelKey") or "discover-native-model",
                aspect=payload.setdefault("aspectRatio", "16:9"),
                resolution=payload.setdefault("resolution", "720p"),
                token="validation-only",
            )
            duration = payload.get("duration")
            if duration is not None and (type(duration) is not int or not 1 <= duration <= 10):
                raise ValueError("duration")
        except (ValueError, TypeError, GFlowError):
            raise HTTPException(
                422,
                "Native reference video requires valid owned image/audio UUIDs "
                "and supported count, aspect, duration/resolution controls",
            ) from None
        payload["referenceImageIds"], payload["referenceAudioIds"] = images, audio
        payload["referenceCharacterIds"] = characters
        payload["referenceSlotIds"] = slot_ids
        return await submit(request, "videos/reference", payload, profile)

    async def native_video_edit(
        request: Request, payload: dict[str, Any]
    ) -> dict[str, Any] | JSONResponse:
        if not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        allowed = {
            "captchaToken",
            "captchaOrder",
            "captchaRetry",
            "email",
            "projectId",
            "referenceVideo_1",
            "prompt",
            "model",
            "modelKey",
            "startFrameIndex_1",
            "endFrameIndex_1",
            "count",
            "async",
            "replyRef",
            "replyUrl",
        }
        allowed.update(f"referenceImage_{i}" for i in range(1, 6))
        allowed.update(f"referenceAudio_{i}" for i in range(1, 4))
        allowed.update(f"character_{i}" for i in range(1, 8))
        check_unknown(payload, allowed)
        if payload.get("model", "omni-flash") != "omni-flash":
            raise HTTPException(422, "referenceVideo_1 requires Omni Flash")
        native_video_controls(payload)
        if type(payload.get("count", 1)) is not int or payload.get("count", 1) != 1:
            raise HTTPException(422, "Native Omni edit supports count=1")
        await translate_input_aliases(
            payload,
            {
                **{f"referenceImage_{i}": "image-or-character" for i in range(1, 6)},
                **{f"referenceAudio_{i}": "voice" for i in range(1, 4)},
                **{f"character_{i}": "character" for i in range(1, 8)},
                "referenceVideo_1": "video",
            },
        )
        profile, project = character_project(payload)
        media = uuid_value(payload.get("referenceVideo_1"), "referenceVideo_1")
        images = [
            uuid_value(payload[f"referenceImage_{i}"], f"referenceImage_{i}")
            for i in range(1, 6)
            if f"referenceImage_{i}" in payload
        ]
        audio = [
            video_audio_value(payload[f"referenceAudio_{i}"])
            for i in range(1, 4)
            if f"referenceAudio_{i}" in payload
        ]
        characters = [
            uuid_value(payload[f"character_{i}"], f"character_{i}")
            for i in range(1, 8)
            if f"character_{i}" in payload
        ]
        slot_ids = {
            key: video_audio_value(payload[key])
            if key.startswith("referenceAudio_")
            else uuid_value(payload[key], key)
            for family, cap in (("referenceImage", 5), ("referenceAudio", 3), ("character", 7))
            for i in range(1, cap + 1)
            if (key := f"{family}_{i}") in payload
        }
        from gflow_cli.api.reference_markers import ReferenceSlot

        slots = (
            None
            if not slot_ids
            else {
                key: ReferenceSlot(
                    "audio"
                    if key.startswith("referenceAudio_")
                    else "character"
                    if key.startswith("character_")
                    else "image",
                    value,
                )
                for key, value in slot_ids.items()
            }
        )
        from gflow_cli.api.native_extension import new_extension_started
        from gflow_cli.api.native_video_edit import video_edit_args
        from gflow_cli.errors import GFlowError

        if "endFrameIndex_1" in payload and type(payload["endFrameIndex_1"]) is not int:
            raise HTTPException(422, "endFrameIndex_1 requires an integer when supplied")
        end_frame = cast(int, payload.get("endFrameIndex_1", 240))
        try:
            video_edit_args(
                new_extension_started(project, media, 1),
                prompt=payload.get("prompt", ""),
                model_key=payload.get("modelKey", ""),
                aspect="16:9",
                token="validation-only",
                start_frame=payload.setdefault("startFrameIndex_1", 0),
                end_frame=end_frame,
                image_ids=tuple(images),
                audio_ids=tuple(audio),
                character_ids=tuple(characters),
                reference_slots=slots,
            )
        except (ValueError, TypeError, GFlowError):
            raise HTTPException(
                422,
                "Omni edit requires native modelKey and a valid24fps trim window",
            ) from None
        payload["referenceVideo_1"] = media
        payload["imageMediaIds"], payload["audioMediaIds"] = images, audio
        payload["characterMediaIds"] = characters
        if slot_ids:
            payload["referenceSlotIds"] = slot_ids
        return await submit(request, "videos/edit", payload, profile)

    @app.post(prefix + "/videos", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def videos(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        if "referenceVideo_1" in payload:
            return await native_video_edit(request, payload)
        if (
            any(payload.get(f"character_{i}") for i in range(1, 8))
            or any(payload.get(f"referenceAudio_{i}") for i in range(1, 6))
            or (
                payload.get("model") == "omni-flash"
                and any(payload.get(f"referenceImage_{i}") for i in range(1, 8))
            )
        ):
            return await native_reference_video(request, payload)
        if not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        allowed = {
            "captchaToken",
            "captchaOrder",
            "captchaRetry",
            "prompt",
            "email",
            "projectId",
            "aspectRatio",
            "count",
            "model",
            "duration",
            "resolution",
            "startImage",
            "endImage",
            "replyUrl",
            "replyRef",
            "async",
        }
        allowed.update(f"referenceImage_{i}" for i in range(1, 8))
        check_unknown(payload, allowed)
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000 or "\x00" in prompt:
            raise HTTPException(422, "prompt requires 1 to 4000 characters without NUL")
        aspect = payload.setdefault("aspectRatio", "16:9")
        if isinstance(aspect, str):
            payload["aspectRatio"] = {"landscape": "16:9", "portrait": "9:16"}.get(aspect, aspect)
        if payload["aspectRatio"] not in ("16:9", "9:16"):
            raise HTTPException(422, "Invalid video aspect ratio")
        if type(payload.setdefault("count", 1)) is not int or not 1 <= payload["count"] <= 4:
            raise HTTPException(422, "Video count requires an integer from 1 to 4")
        model = payload.setdefault("model", "veo-3.1-fast")
        if not isinstance(model, str) or model not in VIDEO_ALIASES:
            raise HTTPException(422, "Unsupported video model")
        if payload.get("duration") is not None and type(payload["duration"]) is not int:
            raise HTTPException(422, "Video duration must be an integer")
        resolution = payload.get("resolution")
        if model != "omni-flash" and resolution == "720p":
            # Native t7a omits the resolution submessage for enum1/720p.
            # Veo has only that default; forwarding a UI resolution selection
            # would look for an absent radio rather than preserve the same wire.
            payload.pop("resolution")
            resolution = None
        elif resolution is not None and (
            resolution not in ("360p", "720p") or model != "omni-flash"
        ):
            raise HTTPException(422, "Veo supports its 720p default; Omni Flash supports 360p/720p")
        if re.search(r"@(reference(?:Image|Audio|Video)?|character|audio)_\d+", prompt, re.I):
            feature_missing("inline useapi reference markers")
        translated = await translate_input_aliases(
            payload,
            {
                "startImage": "image",
                "endImage": "image",
                **{f"referenceImage_{i}": "image" for i in range(1, 8)},
            },
        )
        refs: list[str] = []
        ingredient_ids: list[str] = []
        for field in ("startImage", "endImage", *(f"referenceImage_{i}" for i in range(1, 8))):
            if field in payload:
                payload[field] = uuid_value(payload[field], field)
                refs.append(payload[field])
                if field.startswith("referenceImage_"):
                    ingredient_ids.append(payload[field])
        if payload.get("endImage") and not payload.get("startImage"):
            raise HTTPException(422, "endImage requires startImage")
        if payload.get("startImage") and ingredient_ids:
            raise HTTPException(422, "Video frames and reference ingredients cannot be mixed")
        await cache_alias_images(payload, list(translated.values()))
        profile = pick_account(payload.get("email"), refs, operation="videos")
        try:
            files = {ref: contained_file(store.asset_get(ref)["path"], cfg.root) for ref in refs}
        except ValueError:
            raise HTTPException(422, "Reference bytes are missing from the managed cache") from None
        if any(store.asset_get(ref)["mime"] not in ("image/png", "image/jpeg") for ref in refs):
            raise HTTPException(422, "Video image inputs must be PNG or JPEG assets")
        from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel

        mode = Mode.I2V if payload.get("startImage") else Mode.R2V if ingredient_ids else Mode.T2V
        try:
            GenerateVideoRequest(
                prompt=prompt,
                mode=mode,
                aspect=Aspect.from_cli(payload["aspectRatio"]),
                model=VideoModel.from_cli(VIDEO_ALIASES[model]),
                duration=payload.get("duration"),
                count=payload["count"],
                resolution=resolution,
                start_image=files[payload["startImage"]] if "startImage" in payload else None,
                end_image=files[payload["endImage"]] if "endImage" in payload else None,
                reference_images=tuple(files[ref] for ref in ingredient_ids),
            )
        except ValueError:
            raise HTTPException(
                422, "Unsupported video model/mode/duration/reference combination"
            ) from None
        return await submit(request, "videos", payload, profile)

    @app.post(prefix + "/videos/concatenate", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def concatenate(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        from gflow_cli.api.transports.native_asset_lookup import media_url
        from gflow_cli.selfhost.native_video_cache import cache_native_video, verified_cache_account

        check_unknown(payload, {"media", "email", "projectId", "replyUrl", "replyRef", "async"})
        items = payload.get("media")
        if not isinstance(items, list) or not 2 <= len(cast(list[Any], items)) <= 10:
            raise HTTPException(422, "media requires 2 to 10 video clips")
        normalised: list[dict[str, Any]] = []
        bindings: list[NativeAlias] = []
        alias_ids: set[str] = set()
        for item in cast(list[Any], items):
            if not isinstance(item, dict):
                raise HTTPException(422, "Each media item must be an object")
            typed_item = cast(dict[str, Any], item)
            check_unknown(typed_item, {"mediaGenerationId", "trimStart", "trimEnd"})
            ref = typed_item.get("mediaGenerationId")
            if not isinstance(ref, str) or not 1 <= len(ref) <= 1024:
                raise HTTPException(422, "Each clip requires a managed ID or exact native alias")
            trims: dict[str, Any] = {}
            for field in ("trimStart", "trimEnd"):
                value = typed_item.get(field, 0)
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 10
                ):
                    raise HTTPException(422, "Trims must be finite numbers from0to10seconds")
                trims[field] = value
            if ref.startswith("user:"):
                try:
                    binding = aliases.get(ref)
                except ValueError:
                    raise HTTPException(400, "Unsupported composite video input") from None
                if binding is None:
                    raise HTTPException(404, "Composite input mapping not found")
                if binding.kind != "video":
                    raise HTTPException(400, "Concatenation requires native video aliases")
                verified_alias_account(binding)
                bindings.append(binding)
                ref = binding.media_id
                alias_ids.add(ref)
            normalised.append({"mediaGenerationId": ref, **trims})
        if bindings:
            first = bindings[0]
            scope = (first.profile, first.account, first.project_id)
            if any((b.profile, b.account, b.project_id) != scope for b in bindings):
                raise HTTPException(409, "Video inputs require one account and project")
            if payload.get("email") is not None and payload["email"] != first.account:
                raise HTTPException(403, "Composite video belongs to another account")
            if (
                payload.get("projectId") is not None
                and uuid_value(payload["projectId"], "projectId") != first.project_id
            ):
                raise HTTPException(403, "Composite video belongs to another project")
            payload["email"] = first.account
            payload["projectId"] = first.project_id
        refs = [item["mediaGenerationId"] for item in normalised]
        profile = pick_account(payload.get("email"), refs, allow_native=True)
        native = set(alias_ids)
        projects: set[str] = set()
        for ref in dict.fromkeys(refs):
            try:
                row = store.asset_get(ref)
            except KeyError:
                native.add(uuid_value(ref, "mediaGenerationId"))
                continue
            if row["profile"] != profile or row["mime"] != "video/mp4":
                raise HTTPException(422, "Video cache belongs to another account or media kind")
            try:
                contained_file(row["path"], cfg.root)
            except ValueError:
                raise HTTPException(422, "Managed video bytes are unavailable") from None
            if row["project"]:
                projects.add(row["project"])
            if (
                Path(row["path"])
                .resolve()
                .is_relative_to((cfg.root / "native-video-cache").resolve())
            ):
                native.add(uuid_value(ref, "mediaGenerationId"))
        project = uuid_value(
            payload.get("projectId")
            or (next(iter(projects)) if len(projects) == 1 else cfg.accounts[profile]["project"]),
            "projectId",
        )
        if any(value != project for value in projects):
            raise HTTPException(422, "Video inputs require one project")
        metadata: dict[str, dict[str, Any]] = {}
        if native:
            try:
                verified_cache_account(cfg, store, profile)
            except ValueError:
                raise HTTPException(
                    403, "Native videos require a current verified account"
                ) from None
            try:
                async with asyncio.timeout(180):
                    # All scoped identities and types must pass before any private download.
                    for ref in dict.fromkeys(refs):
                        if ref not in native:
                            continue
                        result = await native_alias_metadata(profile, project, ref)
                        if result.get("kind") != "video":
                            raise HTTPException(
                                502, "Native concatenation input is not a verified video"
                            )
                        try:
                            media_url(result.get("url"), "video")
                        except ValueError:
                            raise HTTPException(502, "Native video URL is unavailable") from None
                        metadata[ref] = result
                    try:
                        for ref, result in metadata.items():
                            await cache_native_video(
                                cfg, store, profile, project, ref, result, subprocess_run
                            )
                    except (ValueError, KeyError, OSError, RuntimeError, TimeoutError):
                        raise HTTPException(502, "Native video cache is unavailable") from None
            except TimeoutError:
                raise HTTPException(502, "Native video cache exceeded its read budget") from None
        if native:
            try:
                verified_cache_account(cfg, store, profile)
            except ValueError:
                raise HTTPException(403, "Native video account changed before queueing") from None
            if bindings:
                verified_alias_account(bindings[0])
        payload["media"] = normalised
        payload["projectId"] = project
        return await submit(request, "videos/concatenate", payload, profile)

    @app.post(prefix + "/videos/upscale", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    @app.post(prefix + "/videos/gif", response_model=None, openapi_extra=FORM_REQUEST_BODY)
    async def export_video(
        request: Request, payload: Annotated[dict[str, Any], Depends(parse_payload)]
    ) -> dict[str, Any] | JSONResponse:
        kind = "videos/gif" if request.url.path.endswith("/gif") else "videos/upscale"
        if kind == "videos/upscale":
            payload.setdefault("operation", "promotion")
        promoting = kind == "videos/upscale" and payload.get("operation") == "promotion"
        if promoting and not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        if "operation" in payload and (
            kind == "videos/gif" or payload["operation"] not in ("promotion", "export")
        ):
            raise HTTPException(422, "operation must be promotion or export for video upscale")
        if (
            promoting
            and "modelKey" in payload
            and (
                not isinstance(payload["modelKey"], str) or not 1 <= len(payload["modelKey"]) <= 200
            )
        ):
            raise HTTPException(422, "modelKey requires a bounded native model key")
        check_unknown(
            payload,
            {
                "mediaGenerationId",
                "email",
                "projectId",
                "resolution",
                "replyUrl",
                "replyRef",
                "async",
                "operation",
            }
            | (
                {"modelKey", "captchaToken", "captchaOrder", "captchaRetry"} if promoting else set()
            ),
        )
        await translate_input_aliases(payload, {"mediaGenerationId": "video"})
        payload["mediaGenerationId"] = uuid_value(
            payload.get("mediaGenerationId"), "mediaGenerationId"
        )
        resolution = payload.setdefault("resolution", "270p" if kind == "videos/gif" else "1080p")
        if promoting and resolution == "4K":
            resolution = payload["resolution"] = "4k"
        if resolution not in (
            ("720p", "1080p", "4k")
            if promoting
            else (("270p",) if kind == "videos/gif" else ("1080p", "720p"))
        ):
            if promoting:
                raise HTTPException(422, "Native promotion requires720p,1080p or4k")
            feature_missing("video export resolution")
        try:
            asset = store.asset_get(payload["mediaGenerationId"])
        except KeyError:
            asset = None
        if not asset and len(cfg.accounts) > 1 and not payload.get("email"):
            raise HTTPException(422, "Unregistered video requires an explicit account")
        profile = pick_account(
            payload.get("email"), [payload["mediaGenerationId"]] if asset else []
        )
        if asset:
            if asset["mime"] != "video/mp4":
                raise HTTPException(422, "Video export requires a video asset")
            if payload.get("projectId") and payload["projectId"] != asset["project"]:
                raise HTTPException(422, "projectId does not own the requested media")
            payload["projectId"] = asset["project"]
        return await submit(request, "videos/promote" if promoting else kind, payload, profile)

    from gflow_cli.selfhost.account_resource_routes import (
        capture_bound_scope,
    )
    from gflow_cli.selfhost.account_resource_routes import (
        mount as mount_resource_reads,
    )

    mount_resource_reads(
        app,
        pick_account=pick_account,
        run=subprocess_run,
        bind_scope=lambda profile, public: capture_bound_scope(cfg, store, profile, public),
    )

    @app.get("/openapi.json")
    async def openapi() -> dict[str, Any]:
        return app.openapi()

    @app.api_route(
        prefix + "/{remaining:path}",
        methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
        include_in_schema=False,
    )
    async def unsupported(remaining: str) -> None:
        feature_missing(remaining)

    return app
