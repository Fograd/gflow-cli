"""Native project timeline reads and reversible trash of measured media batches."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from gflow_cli.api.transports.batchexecute import parse_frames
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.api.transports.migrated_video_upload import is_uuid


def project_media(payload: Any, project_id: str) -> list[dict[str, Any]]:
    """Read measured Zzl0ze timeline identities; do not guess prompt/type from captions."""
    if (
        not isinstance(payload, list)
        or len(cast("list[Any]", payload)) < 3
        or not isinstance(payload[1], list)
    ):
        raise ValueError("Native project timeline has an unsupported shape")
    payload = cast("list[Any]", payload)
    result: list[dict[str, Any]] = []
    members: dict[str, list[str]] = {}
    if not isinstance(payload[2], list):
        raise ValueError("Native timeline has no asset records")
    for candidate in cast("list[Any]", payload[2]):
        if not isinstance(candidate, list):
            continue
        record = cast("list[Any]", candidate)
        if (
            len(record) >= 3
            and record[1] == project_id
            and is_uuid(record[0])
            and is_uuid(record[2])
        ):
            members.setdefault(str(record[2]), []).append(str(record[0]))
    for candidate in cast("list[Any]", payload[1]):
        if not isinstance(candidate, list):
            raise ValueError("Native timeline entry is not an array")
        row = cast("list[Any]", candidate)
        if len(row) < 5 or row[4] != project_id:
            raise ValueError("Native project timeline contains an unrelated project")
        if not isinstance(row[3], list):
            raise ValueError("Native timeline metadata is not an array")
        details = cast("list[Any]", row[3])
        if len(details) < 5:
            raise ValueError("Native project timeline has no media metadata")
        if not is_uuid(row[0]) or not is_uuid(details[4]):
            continue  # Collections/scenes are not media assets.
        result.append(
            {
                "workflow_id": row[0],
                "media_id": details[4],
                "project_id": project_id,
                "caption": details[0] if isinstance(details[0], str) else "",
                "archived": bool(details[2]),
                "batch_media_ids": members.get(str(row[0]), []),
            }
        )
    return result


def trash_payload(media_ids: list[str], media: list[dict[str, Any]], project_id: str) -> list[Any]:
    """Validate the ENTIRE request before forming any mutation."""
    if not is_uuid(project_id) or not 1 <= len(media_ids) <= 100:
        raise ValueError("Trash requires a project UUID and 1 to 100 media UUIDs")
    if len(set(media_ids)) != len(media_ids) or not all(is_uuid(mid) for mid in media_ids):
        raise ValueError("Media identifiers must be distinct UUIDs")
    owned = {row["media_id"]: row for row in media if row["project_id"] == project_id}
    if any(mid not in owned for mid in media_ids):
        raise ValueError("Every requested media must belong to the selected project")
    requested = set(media_ids)
    if any(not owned[mid].get("batch_media_ids", [mid]) for mid in media_ids):
        raise ValueError("Native batch membership is unavailable; refusing archive")
    if any(set(owned[mid].get("batch_media_ids", [mid])) - requested for mid in media_ids):
        raise ValueError("Native trash archives a batch; select every media in the batch")
    rows = [
        [owned[mid]["workflow_id"], None, None, [None, None, 1], project_id] for mid in media_ids
    ]
    return [rows, [["metadata.archived"]]]


async def read_project(page: Any, project_id: str) -> list[dict[str, Any]]:
    if not is_uuid(project_id):
        raise ValueError("Invalid project identifier")
    reply: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    async def on_response(response: Any) -> None:
        if (
            "batchexecute" not in str(response.url)
            or "Zzl0ze" not in str(response.url)
            or reply.done()
        ):
            return
        try:
            text = await response.text()
        except Exception:
            return  # A previous navigation can abort a response body; it is not this read.
        try:
            for rpc, payload in parse_frames(text):
                if rpc == "Zzl0ze":
                    media = project_media(payload, project_id)
                    if not reply.done():
                        reply.set_result(media)
        except Exception as exc:
            if not reply.done():
                reply.set_exception(exc)

    page.on("response", on_response)
    try:
        # A fresh project navigation ensures the SPA emits its authoritative timeline.
        await page.goto(f"https://flow.google.com/project/{project_id}")
        await MigratedComposer().ensure_editor(page, project_id)
        return list(await asyncio.wait_for(reply, timeout=30))
    finally:
        page.remove_listener("response", on_response)


async def trash_media(page: Any, project_id: str, media_ids: list[str]) -> list[str]:
    media = await read_project(page, project_id)
    payload = trash_payload(media_ids, media, project_id)
    # Use the authenticated page's same-origin fetch; never persist or log CSRF/session data.
    response = await page.evaluate(
        """async ({project, payload}) => {
      const wiz = window.WIZ_global_data;
      if (!wiz?.SNlM0e || !wiz?.FdrFJe || !wiz?.cfb2h) throw Error('Flow session unavailable');
      const params = new URLSearchParams({rpcids:'pGCYOe',
        'source-path':'/project/'+project, bl:wiz.cfb2h,'f.sid':wiz.FdrFJe,hl:'en',rt:'c'});
      const body = new URLSearchParams({'f.req':JSON.stringify([
        [['pGCYOe',JSON.stringify(payload),null,'generic']]]),at:wiz.SNlM0e});
      const r = await fetch('/_/AiSandboxAngularFrontend/data/batchexecute?'+params,
        {method:'POST',headers:{'content-type':'application/x-www-form-urlencoded;charset=UTF-8'},body});
      return {status:r.status,text:await r.text()};
    }""",
        {"project": project_id, "payload": payload},
    )
    if response["status"] != 200:
        raise ValueError(f"Native trash failed with HTTP {response['status']}")
    frames = parse_frames(response["text"])
    expected = {row[0] for row in payload[0]}
    acknowledged: set[str] = set()
    for rpc, data in frames:
        if rpc != "pGCYOe" or not isinstance(data, list) or not data:
            continue
        value = cast("list[Any]", data)
        if not isinstance(value[0], list):
            continue
        for row in cast("list[Any]", value[0]):
            if (
                isinstance(row, list)
                and len(cast("list[Any]", row)) >= 5
                and row[0] in expected
                and row[4] == project_id
                and isinstance(row[3], list)
                and len(cast("list[Any]", row[3])) >= 3
                and row[3][2] is True
            ):
                acknowledged.add(str(cast("list[Any]", row)[0]))
    if acknowledged != expected:
        raise ValueError("Native trash was not fully acknowledged; check project before retrying")
    return media_ids
