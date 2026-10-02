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
import sqlite3
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gflow_cli.selfhost.config import (
    MAX_ASSET,
    MODEL_ALIASES,
    VIDEO_ALIASES,
    Settings,
    validate_callback,
)
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
        limit = MAX_ASSET if upload else 65536

        async def limited_receive() -> Message:
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise HTTPException(413, "Request body exceeds the operation limit")
            return message

        await self.app(scope, limited_receive, send)


def create_app(cfg: Settings, *, start_workers: bool = True) -> FastAPI:
    if not cfg.token:
        raise ValueError("Bearer token must be configured")
    store = Store(cfg.root)
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
            worker_tasks.update(
                {
                    profile: asyncio.create_task(worker(cfg, store, profile))
                    for profile in cfg.accounts
                }
            )
            tasks.append(asyncio.create_task(deliver_callbacks(cfg, store)))
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
                if path == "/v1/google-flow/voices" or path.startswith("/v1/google-flow/voices/"):
                    allowed = {"email", "source", "catalog", "projectId"}
                elif path == "/v1/google-flow/characters" or path.startswith(
                    "/v1/google-flow/characters/"
                ):
                    allowed = {"email", "source", "projectId"}
                elif path == "/v1/google-flow/jobs":
                    allowed = {"email", "status", "kind", "limit", "cursor"}
                elif path.startswith("/v1/google-flow/assets/media/"):
                    allowed = {"projectId", "limit", "cursor", "source"}
                elif path.startswith("/v1/google-flow/assets/projects/"):
                    allowed = {"limit", "cursor", "source"}
                elif path.startswith("/v1/google-flow/assets/") and not path.endswith("/download"):
                    allowed = {"raw"}
            if request.method == "DELETE" and path.startswith("/v1/google-flow/characters/"):
                allowed = {"email", "projectId"}
            if set(request.query_params) - allowed or len(
                request.query_params.multi_items()
            ) != len(request.query_params):
                raise HTTPException(
                    501, {"code": "feature_not_implemented", "feature": "query parameters"}
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
    app.add_middleware(BodyLimitMiddleware)
    prefix = "/v1/google-flow"
    from gflow_cli.selfhost.captcha_routes import mount

    mount(app, cfg.root)

    def feature_missing(feature: str) -> None:
        raise HTTPException(
            501,
            {"code": "feature_not_implemented", "feature": feature, "status": "not_implemented"},
        )

    def pick_account(email: str | None, refs: list[str]) -> str:
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
                raise HTTPException(422, "Reference is not registered with this service") from None
        if len(ref_profiles) > 1 or (selected and ref_profiles and selected not in ref_profiles):
            raise HTTPException(422, "References must belong to the selected account")
        if ref_profiles:
            owner = next(iter(ref_profiles))
            if owner not in cfg.accounts:
                raise HTTPException(422, "Reference account is not configured")
            return owner
        if selected:
            return selected
        # Prefer the least loaded account; include running jobs to distribute independent callers.
        with store.connection() as conn:
            counts = dict(
                conn.execute(
                    "SELECT profile,COUNT(*) FROM jobs WHERE state IN ('created','running') "
                    "GROUP BY profile"
                )
            )
        return min(cfg.accounts, key=lambda name: counts.get(name, 0))

    def check_unknown(payload: dict[str, Any], allowed: set[str]) -> None:
        unknown = sorted(set(payload) - allowed)
        if unknown:
            feature_missing(",".join(unknown))

    def uuid_value(value: Any, label: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            raise HTTPException(422, f"{label} must be a bare Google Flow UUID") from None

    async def submit(
        request: Request,
        kind: str,
        payload: dict[str, Any],
        profile: str,
        captcha_token: str | None = None,
    ) -> dict[str, Any]:
        asynchronous = payload.pop("async", False)
        if type(asynchronous) is not bool:
            raise HTTPException(422, "async must be a boolean")
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
            default_project = cfg.accounts[profile]["project"]
        payload["project"] = uuid_value(payload.get("projectId") or default_project, "projectId")
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

        if asynchronous or cfg.sync_wait <= 0:
            return job
        deadline = time.monotonic() + cfg.sync_wait
        while job["status"] in ("created", "running") and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            job = store.get(job["jobId"])
        return job

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
            "healthSource": "operator-attested local profile registration",
            "scope": "local-profile-registration",
        }

    @app.post(prefix + "/accounts")
    async def register_account(payload: dict[str, Any]) -> dict[str, Any]:
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
            raise HTTPException(422, "Profile does not exist; complete local Chrome login first")
        if store.profile_busy(profile):
            raise HTTPException(409, "Profile has an accepted or running job")
        try:
            store.account_set(profile, email, project, enabled, verified)
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "Account handle is already registered to another profile"
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
                "accounts/register-local",
                "accounts/unregister-local",
                "captcha-providers/configuration",
                "captcha-stats",
                "images/seed",
                "images/supplied-captcha-token",
                "images",
                "images/upscale",
                "assets/upload",
                "assets/upload-mp4",
                "assets/media-native-timeline",
                "assets/archive-native-whole-batch",
                "assets/delete-local-cache",
                "assets/read",
                "assets/download",
                "assets/projects",
                "assets/projects-native",
                "assets/media",
                "jobs",
                "voices/read-system",
                "voices/read-system-native",
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
            ],
            "notImplemented": [
                "videos/seed",
                "aspectRatio/auto",
                "characters/voice-binding",
                "voices/custom",
                "images/provider-captcha-generation",
                "captcha-google-refusal-retries",
                "videos/extend",
                "accounts/cookie-import",
                "assets/delete-native-individual",
            ],
            "verification": "Adapters require live verification per account and operation",
        }

    @app.post(prefix + "/images")
    async def images(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
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
        check_unknown(payload, allowed)
        if (
            not isinstance(payload.get("prompt"), str)
            or not 1 <= len(payload["prompt"].strip()) <= 4000
        ):
            raise HTTPException(422, "prompt requires 1 to 4000 characters")
        if re.search(
            r"@(reference(?:Image|Audio|Video)?|character|audio)_\d+", payload["prompt"], re.I
        ):
            feature_missing("inline useapi reference markers")
        model = payload.setdefault("model", "nano-banana-2-lite")
        if not isinstance(model, str) or model not in MODEL_ALIASES:
            raise HTTPException(422, "Unsupported image model")
        if payload.setdefault("aspectRatio", "16:9") not in ("16:9", "4:3", "1:1", "3:4", "9:16"):
            feature_missing("aspectRatio")
        count = payload.setdefault("count", 4)
        if type(count) is not int or not 1 <= count <= 4:
            raise HTTPException(422, "count requires an integer from 1 to 4")
        refs: list[str] = []
        for i in range(1, 11):
            key = f"reference_{i}"
            if key in payload:
                payload[key] = uuid_value(payload[key], key)
                refs.append(payload[key])
        if "seed" in payload and (
            type(payload["seed"]) is not int or not 0 <= payload["seed"] <= 2147483647 - count + 1
        ):
            raise HTTPException(
                422, "seed must be a nonnegative integer with room for count consecutive seeds"
            )
        profile = pick_account(payload.get("email"), refs)
        if any(store.asset_get(ref)["mime"] not in ("image/png", "image/jpeg") for ref in refs):
            raise HTTPException(422, "Image references must be PNG or JPEG assets")
        from gflow_cli.selfhost.captcha_routes import prepare_image_controls

        supplied_token = payload.get("captchaToken")
        prepare_image_controls(payload, cfg.root, persist_token=False)
        if "captchaOrder" in payload or "captchaRetry" in payload:
            feature_missing(
                "provider CAPTCHA solving: Google replacement-token acceptance is unverified"
            )
        return await submit(
            request,
            "images",
            payload,
            profile,
            captcha_token=supplied_token if isinstance(supplied_token, str) else None,
        )

    @app.post(prefix + "/images/upscale")
    async def upscale(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(
            payload,
            {
                "mediaGenerationId",
                "resolution",
                "email",
                "projectId",
                "replyUrl",
                "replyRef",
                "async",
            },
        )
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
        if mime not in ("image/png", "image/jpeg", "video/mp4"):
            raise HTTPException(415, "Upload requires raw PNG, JPEG or MP4")
        rights = request.headers.get("x-flow-rights-confirmed")
        if rights is not None and (rights not in ("true", "false") or mime != "video/mp4"):
            raise HTTPException(
                422, "X-Flow-Rights-Confirmed requires true or false on MP4 uploads only"
            )
        profile = pick_account(email, [])
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > MAX_ASSET:
                raise HTTPException(413, "Asset exceeds 20 MiB")
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
        job = await submit(request, "assets", upload_payload, profile)
        # Keep tee's synchronous upload contract; disconnection leaves the job durable.
        deadline = time.monotonic() + cfg.timeout
        while time.monotonic() < deadline:
            result = store.get(job["jobId"])
            if result["status"] == "completed":
                return result
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
        limit, cursor = pagination(request)
        status = request.query_params.get("status")
        if status and status not in ("created", "running", "completed", "failed", "interrupted"):
            raise HTTPException(422, "Unknown job status")
        email = request.query_params.get("email")
        profile = pick_account(email, []) if email else None
        try:
            return store.job_page(
                limit=limit,
                cursor=cursor,
                profile=profile,
                status=status,
                kind=request.query_params.get("kind"),
            )
        except ValueError:
            raise HTTPException(422, "Invalid job cursor") from None

    @app.get(prefix + "/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found") from None

    @app.get(prefix + "/assets/projects/{email}")
    async def projects(request: Request, email: str) -> dict[str, Any]:
        profile = pick_account(email, [])
        source = request.query_params.get("source", "local")
        if source not in ("local", "google"):
            raise HTTPException(422, "source requires local or google")
        if source == "google":
            cursor = request.query_params.get("cursor")
            if cursor is not None and len(cursor) > 4096:
                raise HTTPException(422, "Native project cursor exceeds 4096 characters")
            if "limit" in request.query_params:
                raise HTTPException(422, "Native project pages have a fixed size of 21")
            code, raw = await subprocess_run(
                [
                    sys.executable,
                    "-m",
                    "gflow_cli.selfhost.native_worker",
                    "projects-list",
                    profile,
                    json.dumps({"cursor": cursor}),
                ],
                60,
            )
            if code:
                raise HTTPException(502, "Google project catalog unavailable")
            result = parse_json_output(raw)
            if result.get("status") != "ok" or not isinstance(result.get("projects"), list):
                raise HTTPException(502, "Google project catalog unavailable")
            return {
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
                "scope": "native Google account project catalog",
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
        source = request.query_params.get("source", "local")
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
            native_rows = [
                {**row, "mediaGenerationId": row["media_id"], "projectId": row["project_id"]}
                for row in result["media"]
            ]
            return {
                **page_slice(request, native_rows, "media"),
                "projectId": project,
                "scope": "google-project-library",
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

    @app.delete(prefix + "/assets/{email}")
    async def delete_assets(
        request: Request, email: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        check_unknown(
            payload,
            {"mediaGenerationIds", "projectId", "localOnly", "async", "replyUrl", "replyRef"},
        )
        profile = pick_account(email, [])
        if payload.get("localOnly") is not True:
            if payload.get("localOnly") not in (None, False):
                raise HTTPException(422, "localOnly must be a boolean")
            project = uuid_value(payload.get("projectId"), "projectId")
            values = payload.get("mediaGenerationIds")
            if not isinstance(values, list) or not 1 <= len(cast(list[Any], values)) <= 100:
                raise HTTPException(422, "Remote archive requires 1 to 100 mediaGenerationIds")
            ids = [uuid_value(value, "mediaGenerationIds") for value in cast(list[Any], values)]
            if len(set(ids)) != len(ids):
                raise HTTPException(422, "mediaGenerationIds must be distinct")
            if any(store.asset_in_use(identifier) for identifier in ids):
                raise HTTPException(409, "Asset is referenced by an active job")
            payload["mediaGenerationIds"] = ids
            payload["projectId"] = project
            return await submit(request, "assets/archive", payload, profile)
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

    @app.get(prefix + "/assets/{media_id}")
    async def get_asset(request: Request, media_id: str) -> Any:
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

    async def native_catalog(request: Request, verb: str, key: str) -> dict[str, Any]:
        profile = pick_account(request.query_params.get("email"), [])
        project = uuid_value(
            request.query_params.get("projectId", cfg.accounts[profile]["project"]), "projectId"
        )
        code, raw = await subprocess_run(
            [
                sys.executable,
                "-m",
                "gflow_cli.selfhost.native_worker",
                verb,
                profile,
                json.dumps({"project_id": project}),
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
                in ("character_binding_outcome_unknown", "character_delete_outcome_unknown")
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
            raise HTTPException(502, detail)
        if verb == "character-delete":
            return {"deleted": result["deleted"], "scope": "native Google project character"}
        return {
            "character": character_item(result["character"], detail=True),
            "scope": "native Google project character",
        }

    @app.post(prefix + "/characters")
    async def create_character(payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(
            payload,
            {
                "email",
                "projectId",
                "displayName",
                "imageReference_1",
                "imageReference_2",
                "personalityNotes",
            },
        )
        character_fields(payload)
        if "displayName" not in payload:
            raise HTTPException(422, "displayName is required")
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
                **(
                    {"personality": payload["personalityNotes"]}
                    if "personalityNotes" in payload
                    else {}
                ),
            },
        )

    @app.patch(prefix + "/characters/{ref}")
    async def patch_character(ref: str, payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(payload, {"email", "projectId", "displayName", "personalityNotes"})
        character_fields(payload)
        if not ({"displayName", "personalityNotes"} & payload.keys()):
            raise HTTPException(422, "At least one character metadata field is required")
        profile, project = character_project(payload)
        return await character_mutation(
            profile,
            "character-update",
            {
                "project_id": project,
                "entity_id": uuid_value(ref, "ref"),
                **({"display_name": payload["displayName"]} if "displayName" in payload else {}),
                **(
                    {"personality": payload["personalityNotes"]}
                    if "personalityNotes" in payload
                    else {}
                ),
            },
        )

    @app.delete(prefix + "/characters/{ref}")
    async def delete_character(request: Request, ref: str) -> dict[str, Any]:
        profile, project = character_project(dict(request.query_params))
        return await character_mutation(
            profile,
            "character-delete",
            {
                "project_id": project,
                "entity_id": uuid_value(ref, "ref"),
            },
        )

    @app.get(prefix + "/characters/{ref}")
    async def get_character(request: Request, ref: str) -> dict[str, Any]:
        if request.query_params.get("source", "google") != "google":
            raise HTTPException(422, "Character source requires google")
        if "catalog" in request.query_params:
            raise HTTPException(422, "catalog is a voice-only option")
        character_project(dict(request.query_params))
        ref = uuid_value(ref, "ref")
        result = await native_catalog(request, "characters-list", "characters")
        row = next((row for row in result["characters"] if row["entity_id"] == ref), None)
        if row is None:
            raise HTTPException(404, "Character not present in the selected project")
        return character_item(row, detail=True)

    @app.get(prefix + "/characters")
    async def characters(request: Request) -> dict[str, Any]:
        if request.query_params.get("source", "google") != "google":
            raise HTTPException(422, "Character source requires google")
        result = await native_catalog(request, "characters-list", "characters")
        result["characters"] = [character_item(row) for row in result["characters"]]
        return result

    @app.get(prefix + "/voices")
    async def voices(request: Request) -> dict[str, Any]:
        if request.query_params.get("source", "system") != "system":
            feature_missing("custom voices")
        catalog = request.query_params.get("catalog", "bundled")
        if catalog not in ("bundled", "google"):
            raise HTTPException(422, "Voice catalog requires bundled or google")
        if catalog == "google":
            result = await native_catalog(request, "voice-presets", "voices")
            result["voices"] = [
                {
                    "ref": row["voice"],
                    "name": row["voice"],
                    "voice": row["voice"],
                    "displayName": row["voice"],
                    "description": row["description"],
                    "source": "system",
                    **({"sampleUrl": row["sample_url"]} if row.get("sample_url") else {}),
                }
                for row in result["voices"]
            ]
            return result
        if "projectId" in request.query_params:
            raise HTTPException(422, "projectId requires catalog=google")
        return {"voices": preset_voices(request), "scope": "bundled system voice catalog"}

    @app.get(prefix + "/voices/{ref}")
    async def voice(request: Request, ref: str) -> dict[str, Any]:
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

    @app.post(prefix + "/videos")
    @app.post(prefix + "/videos/extend")
    async def videos(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        if request.url.path.endswith("/extend"):
            feature_missing("video extension result mapping")
        if not cfg.allow_video:
            raise HTTPException(403, "Video generation requires GFLOW_SELFHOST_ALLOW_VIDEO=1")
        allowed = {
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
        if payload.setdefault("aspectRatio", "16:9") not in ("16:9", "9:16"):
            raise HTTPException(422, "Invalid video aspect ratio")
        if type(payload.setdefault("count", 1)) is not int or not 1 <= payload["count"] <= 4:
            raise HTTPException(422, "Video count requires an integer from 1 to 4")
        model = payload.setdefault("model", "veo-3.1-fast")
        if not isinstance(model, str) or model not in VIDEO_ALIASES:
            raise HTTPException(422, "Unsupported video model")
        if payload.get("duration") is not None and type(payload["duration"]) is not int:
            raise HTTPException(422, "Video duration must be an integer")
        resolution = payload.get("resolution")
        if resolution is not None and (resolution not in ("360p", "720p") or model != "omni-flash"):
            raise HTTPException(
                422, "Explicit resolution is supported only for Omni Flash (360p/720p)"
            )
        if re.search(r"@(reference(?:Image|Audio|Video)?|character|audio)_\d+", prompt, re.I):
            feature_missing("inline useapi reference markers")
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
        profile = pick_account(payload.get("email"), refs)
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

    @app.post(prefix + "/videos/concatenate")
    async def concatenate(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(payload, {"media", "email", "replyUrl", "replyRef", "async"})
        items = payload.get("media")
        if not isinstance(items, list) or not 2 <= len(cast(list[Any], items)) <= 10:
            raise HTTPException(422, "media requires 2 to 10 registered video clips")
        refs: list[str] = []
        normalised: list[dict[str, Any]] = []
        for item in cast(list[Any], items):
            if not isinstance(item, dict):
                raise HTTPException(422, "Each media item must be an object")
            typed_item = cast(dict[str, Any], item)
            check_unknown(typed_item, {"mediaGenerationId", "trimStart", "trimEnd"})
            ref = typed_item.get("mediaGenerationId")
            if not isinstance(ref, str) or not 1 <= len(ref) <= 128:
                raise HTTPException(422, "Each clip requires its registered mediaGenerationId")
            try:
                asset = store.asset_get(ref)
                contained_file(asset["path"], cfg.root)
            except (KeyError, ValueError):
                raise HTTPException(
                    422, "Video clip is not available in the managed registry"
                ) from None
            if asset["mime"] != "video/mp4":
                raise HTTPException(422, "Concatenation requires registered MP4 clips")
            trims = {}
            for field in ("trimStart", "trimEnd"):
                value = typed_item.get(field, 0)
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 10
                ):
                    raise HTTPException(422, "Trims must be finite numbers from 0 to 10 seconds")
                trims[field] = value
            refs.append(ref)
            normalised.append({"mediaGenerationId": ref, **trims})
        profile = pick_account(payload.get("email"), refs)
        payload["media"] = normalised
        return await submit(request, "videos/concatenate", payload, profile)

    @app.post(prefix + "/videos/upscale")
    @app.post(prefix + "/videos/gif")
    async def export_video(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        kind = "videos/gif" if request.url.path.endswith("/gif") else "videos/upscale"
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
            },
        )
        payload["mediaGenerationId"] = uuid_value(
            payload.get("mediaGenerationId"), "mediaGenerationId"
        )
        resolution = payload.setdefault("resolution", "270p" if kind == "videos/gif" else "1080p")
        if resolution not in (("270p",) if kind == "videos/gif" else ("1080p", "720p")):
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
        return await submit(request, kind, payload, profile)

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
