"""Bounded same-origin RPC for measured migrated read/metadata operations only."""

from __future__ import annotations

from typing import Any

from gflow_cli.api._engine import page_owned_evaluate_kwargs
from gflow_cli.api.transports.batchexecute import (
    _wrb_rows,  # pyright: ignore[reportPrivateUsage]
    parse_frames,
    rpc_errors,
)


class NativeMetadataRpcError(ValueError):
    """Correlated native read error; no response text or private reasons."""

    def __init__(self, rpcid: str, code: int | None) -> None:
        self.rpcid = rpcid
        self.code = code
        super().__init__("Native metadata RPC rejected the request")


async def native_rpc(
    page: Any, rpc: str, args: list[Any], source_path: str, *, require_single: bool = False
) -> Any:
    if rpc not in {"UpteDb", "C4BZMd", "rzMKMb", "cz8Z4b", "Sc7aEb", "as29s", "LWkPYd"}:
        raise ValueError("Unsupported native metadata RPC")
    if source_path != "/u/0/" and not source_path.startswith("/project/"):
        raise ValueError("Unsupported native metadata source path")
    result = await page.evaluate(
        """async ({rpc, args, source_path}) => {
      const w = window.WIZ_global_data;
      const q = new URLSearchParams({rpcids:rpc,'source-path':source_path,
        bl:w.cfb2h,'f.sid':w.FdrFJe,hl:'en',rt:'c'});
      const body = new URLSearchParams({'f.req':JSON.stringify([
        [[rpc,JSON.stringify(args),null,'generic']]]),at:w.SNlM0e});
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(),25000);
      try {
      const r = await fetch('/_/AiSandboxAngularFrontend/data/batchexecute?'+q,
        {method:'POST',headers:{'content-type':'application/x-www-form-urlencoded;charset=UTF-8'},body,signal:controller.signal});
      if (!r.ok) return {status:r.status,text:''};
      const reader = r.body.getReader(); const chunks = []; let size = 0;
      while (true) {
        const {done,value} = await reader.read(); if (done) break;
        size += value.length;
        if (size > 262144) {
          await reader.cancel(); throw Error('Project listing exceeded size budget');
        }
        chunks.push(value);
      }
      const bytes = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) {bytes.set(chunk,offset); offset += chunk.length;}
      return {status:r.status,text:new TextDecoder().decode(bytes)};
      } finally {clearTimeout(timer);}
    }""",
        {"rpc": rpc, "args": args, "source_path": source_path},
        **page_owned_evaluate_kwargs(),
    )
    if result["status"] != 200:
        raise ValueError(f"Native Flow operation failed with HTTP {result['status']}")
    rows = [row for row in _wrb_rows(result["text"]) if row[1] == rpc]
    if require_single and len(rows) != 1:
        raise ValueError("Native metadata requires exactly one matching RPC envelope")
    replies = [data for name, data in parse_frames(result["text"]) if name == rpc]
    errors = [error for error in rpc_errors(result["text"]) if error.rpcid == rpc]
    if errors:
        if len(errors) != 1 or len(rows) != 1 or rows[0][2] is not None or replies:
            raise ValueError("Native metadata response is ambiguous")
        raise NativeMetadataRpcError(rpc, errors[0].code)
    if require_single and len(replies) != 1:
        raise ValueError("Native metadata requires exactly one matching RPC response")
    if replies and replies[0] is not None:
        return replies[0]
    raise ValueError("Native Flow operation was not acknowledged; inspect before retrying")
