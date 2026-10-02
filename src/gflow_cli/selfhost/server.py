"""A single daemon owns a durable queue; each configured profile has one worker."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import hmac
import json
import math
import re
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
            tasks = [asyncio.create_task(worker(cfg, store, profile)) for profile in cfg.accounts]
            tasks.append(asyncio.create_task(deliver_callbacks(cfg, store)))
        try:
            yield
        finally:
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
            voice_read = request.method == "GET" and (
                request.url.path == "/v1/google-flow/voices"
                or request.url.path.startswith("/v1/google-flow/voices/")
            )
            allowed: set[str] = {"email", "source"} if voice_read else set()
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
        request: Request, kind: str, payload: dict[str, Any], profile: str
    ) -> dict[str, Any]:
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
        try:
            return store.submit(kind, profile, payload, idem)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        except OverflowError:
            raise HTTPException(429, "Queue is full", headers={"Retry-After": "30"}) from None

    @app.get(prefix + "/accounts")
    async def accounts() -> dict[str, Any]:
        return {
            data["email"]: {
                "profile": profile,
                "health": "OK",
                "plan": "operator-managed",
                "healthSource": "operator-verified configuration",
            }
            for profile, data in cfg.accounts.items()
        }

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
                "images",
                "images/upscale",
                "assets/upload",
                "assets/read",
                "assets/download",
                "assets/projects",
                "assets/media",
                "jobs",
                "voices/read-system",
                "callbacks",
                "idempotency",
            ],
            "videoEnabled": cfg.allow_video,
            "videoAdapters": [
                "videos/text-to-video",
                "videos/upscale",
                "videos/gif",
                "videos/concatenate",
            ],
            "notImplemented": [
                "seed",
                "aspectRatio/auto",
                "characters",
                "voices/custom",
                "captcha-providers",
                "captcha-stats",
                "videos/extend",
                "accounts/write",
                "assets/delete",
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
            "projectId",
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
        profile = pick_account(payload.get("email"), refs)
        if any(store.asset_get(ref)["mime"] not in ("image/png", "image/jpeg") for ref in refs):
            raise HTTPException(422, "Image references must be PNG or JPEG assets")
        return await submit(request, "images", payload, profile)

    @app.post(prefix + "/images/upscale")
    async def upscale(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(
            payload,
            {"mediaGenerationId", "resolution", "email", "projectId", "replyUrl", "replyRef"},
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
        if mime not in ("image/png", "image/jpeg"):
            raise HTTPException(415, "Upload requires raw PNG or JPEG")
        profile = pick_account(email, [])
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > MAX_ASSET:
                raise HTTPException(413, "Asset exceeds 20 MiB")
        valid = (
            data.startswith(b"\x89PNG\r\n\x1a\n")
            if mime == "image/png"
            else data.startswith(b"\xff\xd8\xff")
        )
        if not valid:
            raise HTTPException(422, "Asset signature does not match content type")
        directory = cfg.root / "uploads"
        directory.mkdir(exist_ok=True)
        path = directory / (
            hashlib.sha256(data).hexdigest() + (".png" if mime == "image/png" else ".jpg")
        )
        path.write_bytes(data)
        job = await submit(request, "assets", {"input": str(path), "mime": mime}, profile)
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
    async def jobs() -> dict[str, Any]:
        return {"jobs": store.jobs()}

    @app.get(prefix + "/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found") from None

    @app.get(prefix + "/assets/projects/{email}")
    async def projects(email: str) -> dict[str, Any]:
        profile = pick_account(email, [])
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
            ],
            30,
        )
        if code:
            raise HTTPException(502, "Local project catalog unavailable")
        return {**parse_json_output(output), "scope": "local gflow project catalog"}

    @app.get(prefix + "/assets/media/{email}")
    async def media(email: str) -> dict[str, Any]:
        profile = pick_account(email, [])
        return {
            "media": [
                {
                    **(
                        {"localArtifactId": row["id"]}
                        if "_" in row["id"]
                        else {"mediaGenerationId": row["id"]}
                    ),
                    **({"projectId": row["project"]} if row["project"] else {}),
                    "mimeType": row["mime"],
                }
                for row in store.asset_list(profile)
            ],
            "scope": "selfhost-managed assets",
        }

    @app.get(prefix + "/assets/{media_id}/download")
    async def download(media_id: str) -> FileResponse:
        try:
            row = store.asset_get(media_id)
            path = contained_file(row["path"], cfg.root)
        except (KeyError, ValueError):
            raise HTTPException(404, "Managed asset not found") from None
        return FileResponse(path, media_type=row["mime"], filename=path.name)

    @app.get(prefix + "/assets/{media_id}")
    async def get_asset(media_id: str) -> dict[str, Any]:
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

    @app.get(prefix + "/voices")
    async def voices(request: Request) -> dict[str, Any]:
        return {"voices": preset_voices(request), "scope": "bundled system voice catalog"}

    @app.get(prefix + "/voices/{ref}")
    async def voice(request: Request, ref: str) -> dict[str, Any]:
        match = next(
            (item for item in preset_voices(request) if item["ref"].casefold() == ref.casefold()),
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
            raise HTTPException(
                403,
                "Video operations spend credits; "
                "enable GFLOW_SELFHOST_ALLOW_VIDEO=1 after verification",
            )
        if request.url.path.endswith("/extend"):
            feature_missing("video extension result mapping")
        kind = "videos"
        check_unknown(
            payload,
            {
                "prompt",
                "email",
                "projectId",
                "aspectRatio",
                "count",
                "model",
                "duration",
                "mediaGenerationId",
                "replyUrl",
                "replyRef",
            },
        )
        if (
            not isinstance(payload.get("prompt"), str)
            or not 1 <= len(payload["prompt"].strip()) <= 4000
        ):
            raise HTTPException(422, "prompt requires 1 to 4000 characters")
        if payload.setdefault("aspectRatio", "16:9") not in ("16:9", "9:16"):
            raise HTTPException(422, "Invalid video aspect ratio")
        if type(payload.setdefault("count", 1)) is not int or not 1 <= payload["count"] <= 4:
            raise HTTPException(422, "Invalid video count")
        model = payload.setdefault("model", "veo-3.1-fast")
        if model is not None and (not isinstance(model, str) or model not in VIDEO_ALIASES):
            feature_missing("video model")
        if payload["count"] != 1:
            feature_missing("multi-video output mapping")
        if payload.get("duration") is not None and type(payload["duration"]) is not int:
            raise HTTPException(422, "Video duration must be an integer")
        if payload.get("duration") not in (None, 4, 6, 8, 10):
            raise HTTPException(422, "Invalid video duration")
        if "mediaGenerationId" in payload:
            feature_missing("video mediaGenerationId")
        if re.search(
            r"@(reference(?:Image|Audio|Video)?|character|audio)_\d+", payload["prompt"], re.I
        ):
            feature_missing("inline useapi reference markers")
        from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel

        try:
            GenerateVideoRequest(
                prompt=payload["prompt"],
                mode=Mode.T2V,
                aspect=Aspect.from_cli(payload["aspectRatio"]),
                model=VideoModel.from_cli(VIDEO_ALIASES[model]) if model else None,
                duration=payload.get("duration"),
                count=payload["count"],
            )
        except ValueError:
            raise HTTPException(422, "Unsupported video model/duration combination") from None
        profile = pick_account(payload.get("email"), [])
        return await submit(request, kind, payload, profile)

    @app.post(prefix + "/videos/concatenate")
    async def concatenate(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        check_unknown(payload, {"media", "email", "replyUrl", "replyRef"})
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
            {"mediaGenerationId", "email", "projectId", "resolution", "replyUrl", "replyRef"},
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
