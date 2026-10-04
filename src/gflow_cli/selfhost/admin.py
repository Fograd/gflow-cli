"""Loopback-only CapSolver key editor, independent of the REST queue/bearer."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from gflow_cli.selfhost.admin_page import PAGE
from gflow_cli.selfhost.captcha import ProviderKeys, Solver, SolverError


def create_app(
    keys: ProviderKeys | None = None,
    *,
    port: int = 8845,
    client: httpx.AsyncClient | None = None,
) -> FastAPI:
    if not 1 <= port <= 65535:
        raise ValueError("Invalid settings port")
    storage = keys or ProviderKeys(Path.home() / ".config/homelab")
    csrf = secrets.token_hex(32)
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    busy = False

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        connection = client or httpx.AsyncClient(
            timeout=15, follow_redirects=False, trust_env=False
        )
        app.state.connection = connection
        try:
            yield
        finally:
            if client is None:
                await connection.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security(request: Request, call_next: Any) -> Response:
        if request.headers.get("host") not in hosts:
            response = JSONResponse({"detail": "Local settings host required"}, status_code=400)
        elif request.method == "POST" and (
            request.headers.get("origin") not in origins
            or not hmac.compare_digest(
                request.headers.get("x-csrf-token", "").encode(), csrf.encode()
            )
        ):
            response = JSONResponse({"detail": "Settings request denied"}, status_code=403)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response

    async def payload(request: Request, allowed: set[str]) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise HTTPException(415, "JSON required")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 2048:
                raise HTTPException(413, "Settings request is too large")
            body.extend(chunk)
        try:
            data: Any = json.loads(body)
        except ValueError:
            raise HTTPException(422, "Invalid settings request") from None
        if not isinstance(data, dict) or set(cast(dict[str, Any], data)) - allowed:
            raise HTTPException(422, "Invalid settings request")
        return cast(dict[str, Any], data)

    @app.get("/", response_class=HTMLResponse)
    async def page() -> HTMLResponse:
        nonce = secrets.token_hex(16)
        return HTMLResponse(
            PAGE.replace("__CSRF__", csrf).replace("__NONCE__", nonce),
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; connect-src 'self'; "
                    f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
                )
            },
        )

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        public = await run_in_threadpool(storage.public)
        return {"configured": "CapSolver" in public, "generationEnabled": "CapSolver" in public}

    @app.post("/api/save")
    async def save(request: Request) -> dict[str, Any]:
        data = await payload(request, {"key"})
        key = data.get("key")
        if not isinstance(key, str) or not key:
            raise HTTPException(422, "Enter a valid CapSolver key")
        try:
            await run_in_threadpool(storage.update, {"CapSolver": key})
        except ValueError:
            raise HTTPException(422, "Enter a valid CapSolver key") from None
        return {"configured": True}

    @app.post("/api/remove")
    async def remove(request: Request) -> dict[str, Any]:
        await payload(request, set())
        await run_in_threadpool(storage.update, {"CapSolver": ""})
        return {"configured": False}

    @app.post("/api/check")
    async def check(request: Request) -> dict[str, Any]:
        nonlocal busy
        await payload(request, set())
        if busy:
            raise HTTPException(429, "A connection check is already running")
        busy = True
        try:
            key = await run_in_threadpool(storage.get, "CapSolver")
            if not key:
                raise HTTPException(422, "Save a CapSolver key first")
            try:
                async with asyncio.timeout(15):
                    balance = await Solver(client=app.state.connection).balance(key)
            except (SolverError, httpx.HTTPError, TimeoutError, ValueError):
                raise HTTPException(502, "CapSolver could not verify the key or balance") from None
            return {"verified": True, "balance": balance, "generationEnabled": True}
        finally:
            busy = False

    return app


def main() -> None:
    port = int(os.environ.get("GFLOW_CAPSOLVER_GUI_PORT", "8845"))
    uvicorn.run(
        create_app(port=port), host="127.0.0.1", port=port, access_log=False, log_level="warning"
    )


if __name__ == "__main__":
    main()
