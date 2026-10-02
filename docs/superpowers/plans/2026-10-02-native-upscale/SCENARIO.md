# Native upscale scenarios

D1/D2: preserve profile isolation and page-owned captcha, report RPC failures without guessing retryability. D3: select numeric scale tokens and stable Material ligatures; disabled differs from missing. D4: no generation is submitted; output naming follows upstream overwrite behaviour. D5: check out/in the page on every result. D6: no DB migration. D7/D9/D11: reject invalid IDs, invalid bytes, undecodable/oversize payloads, missing records and timeouts. D8: retain storage path helpers. D10: existing headed configuration. D12: log metadata only. D13: live MCP image twin, offline video adapter checks.

Must cover: native2K produces actual doubled dimensions; Pro4K disabled before request; MCP image returns usable file; malformed/oversize payloads rejected; listener and browser hooks restored after failure. Video live verification requires an existing clip and remains explicitly unverified if no clip exists.
