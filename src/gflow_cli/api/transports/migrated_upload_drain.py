"""Drain a scoped clone to work around Chromium's lost streamed CDP response body.

The original fetch promise/response and canonical response.text() remain unchanged.
No acknowledgement bytes are retained or used here; only completion/counts cross
the page boundary. This bounds the drain budget, not Chromium's internal buffers.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from gflow_cli.api._engine import page_owned_evaluate_kwargs

if TYPE_CHECKING:
    from playwright.async_api import Page

MAX_DRAIN_BYTES = 1024 * 1024
DRAIN_TIMEOUT_MS = 60_000
_RPC_BUDGETS = {
    "maseQ": (MAX_DRAIN_BYTES, DRAIN_TIMEOUT_MS),
    "Zzl0ze": (2 * 1024 * 1024, 30_000),
    "ogiZ0b": (2 * 1024 * 1024, 180_000),
}

INSTALL_SCRIPT = r"""({key, project, limit, timeoutMs, rpc='maseQ'}) => {
  const original = window.fetch;
  if (typeof original !== 'function' || window[key]) return false;
  let active = true, reader = null, pending = null;
  const state = {matches:0, complete:false, bytes:0};
  const cancel = () => {
    if (reader) {
      try { void reader.cancel().catch(() => {}); } catch {}
    }
  };
  const matches = (input, init) => {
    try {
      const url = new URL(input instanceof Request ? input.url : input, location.href);
      const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
      return String(method).toUpperCase() === 'POST'
        && url.origin === 'https://flow.google.com' && !url.username && !url.password
        && url.pathname === '/_/AiSandboxAngularFrontend/data/batchexecute'
        && !url.hash && url.searchParams.getAll('rpcids').length === 1
        && url.searchParams.get('rpcids') === rpc
        && url.searchParams.getAll('source-path').length === 1
        && url.searchParams.get('source-path') === '/project/' + project;
    } catch { return false; }
  };
  const wrapper = function(...args) {
    const candidate = active && matches(args[0], args[1]);
    const promise = Reflect.apply(original, this, args);
    if (candidate) {
      state.matches++;
      if (state.matches > 1) { state.complete = false; cancel(); return promise; }
      try { pending = promise.then(async response => {
        let eof = false;
        try {
          if (!active || response.status !== 200 || response.redirected
              || !matches(response.url, {method:'POST'})) return;
          reader = response.clone().body.getReader();
          for (;;) {
            const {done, value} = await reader.read();
            if (done) { eof = true; break; }
            state.bytes += value.byteLength;
            if (!active || state.bytes > limit) break;
            // Discard immediately. Never retain or export response chunks.
          }
          state.complete = active && eof && state.matches === 1
            && state.bytes > 0 && state.bytes <= limit;
        } catch { state.complete = false; }
        finally {
          if (!eof) cancel(); // Never await cancellation of one tee branch.
          try { reader?.releaseLock(); } catch {}
          reader = null;
        }
      }, () => {});
        void pending.catch(() => { state.complete = false; });
      } catch { state.complete = false; }
    }
    return promise; // Preserve the exact original promise, not a chained substitute.
  };
  let expire;
  const expired = new Promise(resolve => { expire = resolve; });
  const cleanup = () => {
    active = false; cancel(); clearTimeout(timer);
    if (window.fetch === wrapper) window.fetch = original;
    expire();
  };
  const timer = setTimeout(cleanup, timeoutMs);
  window[key] = {
    result:async () => {
      if (pending) await Promise.race([pending, expired]);
      return {matches:state.matches, complete:state.complete, bytes:state.bytes};
    },
    close:() => { cleanup(); delete window[key]; }
  };
  window.fetch = wrapper;
  return true;
}"""

CONTROL_SCRIPT = r"""async ({key, action}) => {
  const state = window[key];
  if (!state) return null;
  if (action === 'close') { state.close(); return null; }
  return await state.result();
}"""


@dataclass(frozen=True)
class DrainObservation:
    observed: bool = False
    complete: bool = False
    bytes: int = 0
    matches: int = 0
    limit: int = MAX_DRAIN_BYTES

    @property
    def allows_ack(self) -> bool:
        return not self.observed or (
            self.complete and self.matches == 1 and 0 < self.bytes <= self.limit
        )


class UploadResponseDrain:
    """Scoped canonical RPC body workaround; internal measured readers only."""

    def __init__(self, page: Page, project_id: str, *, rpc: str = "maseQ") -> None:
        if rpc not in _RPC_BUDGETS:
            raise ValueError("Unsupported native response drain")
        self.page = page
        self.project_id = project_id
        self.rpc = rpc
        self.limit, self.timeout_ms = _RPC_BUDGETS[rpc]
        self.key = "__gflowResponseDrain_" + uuid4().hex
        self.installed = False
        self.attempted = False
        self.session: Any = None
        self.script_id: str | None = None

    async def install(self, *, navigation: bool = False) -> None:
        self.attempted = True
        params = {
            "key": self.key,
            "project": self.project_id,
            "limit": self.limit,
            "timeoutMs": self.timeout_ms,
            "rpc": self.rpc,
        }
        try:
            if navigation:
                # Page.add_init_script has no removal API. Own the CDP registration
                # instead, and expire it absolutely even if cleanup is interrupted.
                deadline = int(time.time() * 1000) + self.timeout_ms
                project_url = json.dumps("/project/" + self.project_id)
                script = (
                    "(() => { const deadline=" + str(deadline) + ";"
                    "if(window.top!==window || location.origin!=='https://flow.google.com'"
                    " || location.pathname!==" + project_url + " || Date.now()>=deadline)return;"
                    "const args=" + json.dumps(params) + ";"
                    "args.timeoutMs=Math.max(1,deadline-Date.now());"
                    "(" + INSTALL_SCRIPT + ")(args); })();"
                )
                self.session = await self.page.context.new_cdp_session(self.page)
                await self.session.send("Page.enable")
                registered: Any = await self.session.send(
                    "Page.addScriptToEvaluateOnNewDocument", {"source": script}
                )
                identifier: Any = (
                    cast("dict[str, Any]", registered).get("identifier")
                    if isinstance(registered, dict)
                    else None
                )
                if not isinstance(identifier, str) or not identifier:
                    return
                self.script_id = identifier
                self.installed = True
            else:
                self.installed = (
                    await self.page.evaluate(INSTALL_SCRIPT, params, **page_owned_evaluate_kwargs())
                    is True
                )
        except Exception:  # noqa: BLE001 - unsupported hooks preserve the canonical path
            self.installed = False

    async def result(self) -> DrainObservation:
        if not self.installed:
            return DrainObservation(limit=self.limit)
        try:
            raw: Any = await self.page.evaluate(
                CONTROL_SCRIPT,
                {"key": self.key, "action": "result"},
                **page_owned_evaluate_kwargs(),
            )
        except Exception:  # noqa: BLE001 - an observed stream cannot be confirmed
            return DrainObservation(observed=True, limit=self.limit)
        if not isinstance(raw, dict):
            return DrainObservation(observed=True, limit=self.limit)
        payload = cast("dict[str, Any]", raw)
        matches, size = payload.get("matches"), payload.get("bytes")
        if type(matches) is not int or type(size) is not int or matches < 0 or size < 0:
            return DrainObservation(observed=True, limit=self.limit)
        if matches == 0 and (payload.get("complete") is not False or size != 0):
            return DrainObservation(observed=True, limit=self.limit)
        return DrainObservation(
            observed=matches > 0,
            complete=payload.get("complete") is True,
            bytes=size,
            matches=matches,
            limit=self.limit,
        )

    async def close(self) -> None:
        if not self.attempted:
            return
        cancelled: asyncio.CancelledError | None = None
        try:
            await self.page.evaluate(
                CONTROL_SCRIPT,
                {"key": self.key, "action": "close"},
                **page_owned_evaluate_kwargs(),
            )
        except asyncio.CancelledError as error:
            cancelled = error
        except Exception:  # noqa: BLE001 - navigation may discard our page state
            pass
        if self.session is not None:
            try:
                if self.script_id:
                    await self.session.send(
                        "Page.removeScriptToEvaluateOnNewDocument", {"identifier": self.script_id}
                    )
            except asyncio.CancelledError as error:
                cancelled = cancelled or error
            except Exception:  # noqa: BLE001 - absolute expiry bounds orphaned registrations
                pass
            try:
                await self.session.detach()
            except asyncio.CancelledError as error:
                cancelled = cancelled or error
            except Exception:  # noqa: BLE001 - page/browser may already have closed
                pass
        self.installed = self.attempted = False
        self.session = self.script_id = None
        if cancelled:
            raise cancelled
