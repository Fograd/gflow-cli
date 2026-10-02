"""Confirm upscale request correlation fields via an existing 2K image ($0).

Measured media and resolution fields settle the correlation contract. Missing fields
mean do not infer a new shape. Reuses gflow's leased in-process client.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import build_client, default_out_path, resolve_profile_dir

from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.api.transports.migrated_upscale import upscale_image_migrated


async def main() -> None:
    fields = []
    async with build_client(resolve_profile_dir(os.environ["GFLOW_CLI_E2E_PROFILE"])) as client:
        page = await client._checkout_page()

        def request(req):
            if "rpcids=SPrCad" not in req.url:
                return
            wire = json.loads(parse_qs(req.post_data)["f.req"][0])
            args = json.loads(wire[0][0][1])
            fields.append(
                {
                    "media": args[0],
                    "resolution": args[1],
                    "project_present": os.environ["GFLOW_CLI_E2E_UPSCALE_PROJECT"]
                    in json.dumps(args),
                }
            )

        page.on("request", request)
        try:
            data = await upscale_image_migrated(
                page,
                project_id=os.environ["GFLOW_CLI_E2E_UPSCALE_PROJECT"],
                media_id=os.environ["GFLOW_CLI_E2E_UPSCALE_MEDIA"],
                target_resolution=TargetResolution.RES_2K,
            )
            print(json.dumps({"bytes": len(data), "fields": fields}))
            default_out_path("selfhost_upscale_correlation").write_text(json.dumps(fields))
        finally:
            client._checkin_page(page)


asyncio.run(main())
