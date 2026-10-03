"""Bounded same-origin RPC for measured migrated read/metadata operations only."""

from __future__ import annotations

from typing import Any

from gflow_cli.api.transports.batchexecute import parse_frames


async def native_rpc(page: Any, rpc: str, args: list[Any], source_path: str) -> Any:
    if rpc not in {"UpteDb", "C4BZMd", "rzMKMb", "cz8Z4b", "Sc7aEb", "as29s"}:
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
    )
    if result["status"] != 200:
        raise ValueError(f"Native Flow operation failed with HTTP {result['status']}")
    for name, data in parse_frames(result["text"]):
        if name == rpc:
            return data
    raise ValueError("Native Flow operation was not acknowledged; inspect before retrying")
