"""Bounded original pro2/pro3 cold navigation; no imports, auth retries or paid calls.

Two matching fresh principals plus project reads prove current access and cold reuse.
Cookie/Set-Cookie changes measure browser housekeeping only, never authentication
renewal across an expiry boundary. A challenge/unknown failure proves no renewal.
No values, headers, emails, project IDs or private URLs are emitted or persisted.
"""

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from _spike_common import build_client, resolve_profile_dir

from gflow_cli.auth.native_identity import read_native_identity
from gflow_cli.selfhost.account_marker import read_verified_account


def profile_memory(profile):
    """Linux browser tree PSS; does not signal or attach to any process."""
    rows = {}
    roots = set()
    for folder in Path("/proc").glob("[0-9]*"):
        try:
            cmd = (folder / "cmdline").read_bytes().split(b"\0")
            status = (folder / "status").read_text()
            parent = int(next(line.split()[1] for line in status.splitlines()
                              if line.startswith("PPid:")))
            pid = int(folder.name)
            rows[pid] = (parent, folder)
            if ("--user-data-dir=" + str(profile)).encode() in cmd:
                roots.add(pid)
        except (OSError, StopIteration, ValueError):
            pass
    owned = roots.copy()
    while True:
        more = {pid for pid, (parent, _) in rows.items() if parent in owned} - owned
        if not more:
            break
        owned.update(more)
    pss = 0
    for pid in owned:
        try:
            lines = (rows[pid][1] / "smaps_rollup").read_text().splitlines()
            pss += int(next(line.split()[1] for line in lines if line.startswith("Pss:")))
        except (OSError, StopIteration, ValueError):
            pass
    return {"processes": len(owned), "pssMiB": round(pss / 1024, 1)}


def cookie_snapshot(cookies):
    # Kept only inside this process to compare natural navigation, never copied.
    return {(c["name"], c["domain"], c["path"]): (c["value"], c["expires"])
            for c in cookies if c["domain"].lstrip(".") in
            {"google.com", "accounts.google.com", "flow.google.com", "labs.google"}}


async def run(profile, project, opens=2):
    target = resolve_profile_dir(profile)
    expected = read_verified_account(target)
    assert expected, "Expected saved identity required"
    disk = (target.stat().st_dev, target.stat().st_ino)
    output = {"profile": profile, "before": profile_memory(target), "opens": [],
              "automaticRenewalProved": False, "generationRequests": 0, "solverRequests": 0}
    for _ in range(opens):
        evidence = {"checkedAt": datetime.now(UTC).isoformat(), "setCookieResponses": 0,
                    "setCookieNames": [], "googleAccountResponsePaths": []}
        async with build_client(target) as client:
            page, context = client._page, client._context
            assert page is not None and context is not None
            identity = await read_native_identity(page)
            evidence["identityMatched"] = identity.casefold() == expected.casefold()
            assert evidence["identityMatched"], "Current Google identity differs"
            await client.list_native_media(project)
            evidence["projectAccess"] = True
            before = cookie_snapshot(await context.cookies())

            async def response_headers(response):
                host = urlsplit(response.url).hostname
                if host in {"google.com", "accounts.google.com", "flow.google.com"}:
                    headers = await response.headers_array()
                    names = {h["value"].partition("=")[0] for h in headers
                             if h["name"].lower() == "set-cookie"}
                    if names:
                        evidence["setCookieResponses"] += 1
                        evidence["setCookieNames"] = sorted(set(evidence["setCookieNames"]) |
                            {n for n in names if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", n)})
                    path = urlsplit(response.url).path
                    if host == "accounts.google.com" and re.fullmatch(r"/[A-Za-z/]{1,80}", path):
                        evidence["googleAccountResponsePaths"] = sorted(
                            set(evidence["googleAccountResponsePaths"]) | {path})

            context.on("response", response_headers)
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            identity = await read_native_identity(page)
            assert identity.casefold() == expected.casefold(), "Reload identity differs"
            await client.list_native_media(project)
            after = cookie_snapshot(await context.cookies())
            shared = before.keys() & after.keys()
            evidence["cookieValuesChanged"] = sum(before[k][0] != after[k][0] for k in shared)
            evidence["cookieExpiriesExtended"] = sum(after[k][1] > before[k][1] for k in shared)
            evidence["changedCookieNames"] = sorted({k[0] for k in shared if before[k][0] != after[k][0]})
            evidence["extendedCookieNames"] = sorted({k[0] for k in shared if after[k][1] > before[k][1]})
            evidence["pages"] = len(context.pages)
            evidence["activeMemory"] = profile_memory(target)
            evidence["host"] = urlsplit(page.url).hostname
            context.remove_listener("response", response_headers)
        evidence["afterCloseMemory"] = profile_memory(target)
        output["opens"].append(evidence)
    output["originalDirectoryPreserved"] = disk == (target.stat().st_dev, target.stat().st_ino)
    output["markerPreserved"] = expected == read_verified_account(target)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("pro2", "pro3"), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--opens", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(asyncio.wait_for(run(args.profile, args.project, args.opens), 240)), indent=2))
