"""Private solver configuration and bounded Enterprise v3 provider clients."""

from __future__ import annotations

import asyncio
import fcntl
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

PROVIDERS = ("CapSolver", "2Captcha")
_KEY_NAMES = {"CapSolver": "GFLOW_CAPSOLVER_KEY", "2Captcha": "GFLOW_2CAPTCHA_KEY"}
_ENDPOINTS = {"CapSolver": "https://api.capsolver.com", "2Captcha": "https://api.2captcha.com"}


class SolverError(Exception):
    """A deliberately redacted provider failure."""


@dataclass(frozen=True)
class Solution:
    token: str = field(repr=False)
    provider: str
    task_id: str


class ProviderKeys:
    """Store only provider secrets in a mode-600 file outside the queue."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "secrets.env"

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        from dotenv import dotenv_values

        result: dict[str, str] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            for provider, name in _KEY_NAMES.items():
                if line.startswith(name + "="):
                    from io import StringIO

                    value = dotenv_values(stream=StringIO(line), interpolate=False).get(name)
                    if value:
                        result[provider] = value
        return result

    def get(self, provider: str) -> str:
        return self._read().get(provider, "")

    def public(self) -> dict[str, str]:
        return {name: "***configured***" for name, value in self._read().items() if value}

    def update(self, values: dict[str, Any]) -> dict[str, str]:
        if any(
            name not in PROVIDERS
            or not isinstance(value, str)
            or (value and not re.fullmatch(r"[A-Za-z0-9_-]{1,500}", value))
            for name, value in values.items()
        ):
            raise ValueError("Only CapSolver and 2Captcha key strings are supported")
        with (self.path.parent / ".gflow-captcha.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            return self._update_locked(values)

    def _update_locked(self, values: dict[str, Any]) -> dict[str, str]:
        current = self._read()
        for name, value in values.items():
            if value:
                current[name] = value
            else:
                current.pop(name, None)
        fd, name = tempfile.mkstemp(prefix=".captcha-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                lines = (
                    self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
                )
                names = tuple(name + "=" for name in _KEY_NAMES.values())
                lines = [line for line in lines if not line.startswith(names)]
                lines.extend(
                    _KEY_NAMES[key] + "=" + json.dumps(value) for key, value in current.items()
                )
                file.write("\n".join(lines) + "\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
        return self.public()


class Solver:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120,
        poll_interval: float = 2,
    ):
        self.client = client
        self.timeout = timeout
        self.poll_interval = poll_interval

    async def balance(self, key: str) -> float:
        """Read CapSolver balance only; never return package or provider error bodies."""
        if not key:
            raise SolverError("CapSolver key is not configured")
        client = self.client or httpx.AsyncClient(
            timeout=15, follow_redirects=False, trust_env=False
        )
        try:
            async with asyncio.timeout(15):
                data = await self._post(client, "CapSolver", "/getBalance", {"clientKey": key})
                value = data.get("balance")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise SolverError("CapSolver returned an invalid balance")
                balance = float(value)
                if not math.isfinite(balance) or balance < 0:
                    raise SolverError("CapSolver returned an invalid balance")
                return balance
        except (httpx.HTTPError, TimeoutError, ValueError, OverflowError):
            raise SolverError("CapSolver balance request failed or exceeded its deadline") from None
        finally:
            if self.client is None:
                await client.aclose()

    async def solve(self, provider: str, key: str, url: str, sitekey: str, action: str) -> Solution:
        if provider not in PROVIDERS or not key:
            raise SolverError("Requested solver is not configured")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in ("flow.google.com", "labs.google"):
            raise SolverError("Solver URL is not an approved Flow origin")
        task: dict[str, Any] = {
            "type": "ReCaptchaV3EnterpriseTaskProxyLess"
            if provider == "CapSolver"
            else "RecaptchaV3TaskProxyless",
            "websiteURL": url,
            "websiteKey": sitekey,
            "pageAction": action,
        }
        if provider == "2Captcha":
            task.update(isEnterprise=True, minScore=0.9)
        client = self.client or httpx.AsyncClient(
            timeout=20, follow_redirects=False, trust_env=False
        )
        try:
            async with asyncio.timeout(self.timeout):
                result = await self._post(
                    client, provider, "/createTask", {"clientKey": key, "task": task}
                )
                task_id = result.get("taskId")
                if not isinstance(task_id, (str, int)) or isinstance(task_id, bool):
                    raise SolverError("Solver did not return a task identifier")
                while True:
                    await asyncio.sleep(self.poll_interval)
                    result = await self._post(
                        client, provider, "/getTaskResult", {"clientKey": key, "taskId": task_id}
                    )
                    if result.get("status") == "ready":
                        solution = result.get("solution")
                        token = (
                            cast(dict[str, Any], solution).get("gRecaptchaResponse")
                            if isinstance(solution, dict)
                            else None
                        )
                        if not isinstance(token, str) or not 20 <= len(token) <= 20000:
                            raise SolverError("Solver returned an invalid solution")
                        return Solution(token=token, provider=provider, task_id=str(task_id))
                    if result.get("status") != "processing":
                        raise SolverError("Solver returned an unknown task state")
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise SolverError("Solver request failed or exceeded its deadline") from None
        finally:
            if self.client is None:
                await client.aclose()

    @staticmethod
    async def _post(
        client: httpx.AsyncClient, provider: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with client.stream(
            "POST", _ENDPOINTS[provider] + path, json=payload, follow_redirects=False
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                if len(body) + len(chunk) > 65536:
                    raise SolverError("Solver response exceeded its limit")
                body.extend(chunk)
        data: Any = json.loads(body)
        if not isinstance(data, dict) or cast(dict[str, Any], data).get("errorId") != 0:
            raise SolverError("Solver rejected the request")
        return cast(dict[str, Any], data)


class CaptchaStats:
    """Aggregate observations only; no tokens, keys or task bodies are retained."""

    def __init__(self, root: Path):
        import sqlite3

        self.path = root / "captcha-stats.sqlite3"
        self._starts: dict[tuple[str, str], float] = {}
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS stats "
                "(provider TEXT,phase TEXT,count INTEGER,PRIMARY KEY(provider,phase))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events "
                "(id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,provider TEXT NOT NULL,"
                "phase TEXT NOT NULL)"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
            if "duration_ms" not in columns:
                conn.execute("ALTER TABLE events ADD COLUMN duration_ms INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS events_timestamp ON events(timestamp)")
        self.path.chmod(0o600)

    def record(self, provider: str, phase: str) -> None:
        import sqlite3

        if provider not in (*PROVIDERS, "supplied") or phase not in (
            "solveStarted",
            "solveFailed",
            "solved",
            "submitted",
            "accepted",
            "rejected",
            "unknown",
        ):
            raise ValueError("Unknown CAPTCHA observation")
        now = time.monotonic()
        duration: int | None = None
        if phase in {"solveStarted", "submitted"}:
            self._starts[(provider, phase)] = now
        else:
            starting_phase = "solveStarted" if phase in {"solved", "solveFailed"} else "submitted"
            started = self._starts.pop((provider, starting_phase), None)
            if started is not None and 0 <= now - started <= 3600:
                duration = round((now - started) * 1000)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO stats VALUES(?,?,1) ON CONFLICT(provider,phase) "
                "DO UPDATE SET count=count+1",
                (provider, phase),
            )
            from datetime import UTC, datetime

            conn.execute(
                "INSERT INTO events(timestamp,provider,phase,duration_ms) VALUES(?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    provider,
                    phase,
                    duration,
                ),
            )

    def public(self) -> dict[str, Any]:
        import sqlite3

        result: dict[str, Any] = {"scope": "this-self-hosted-instance", "providers": {}}
        with sqlite3.connect(self.path) as conn:
            for provider, phase, count in conn.execute("SELECT provider,phase,count FROM stats"):
                result["providers"].setdefault(provider, {})[phase] = count
        return result
