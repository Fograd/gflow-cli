"""Native project timeline reads and reversible trash of measured media batches."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from gflow_cli.api.transports.batchexecute import parse_frames
from gflow_cli.api.transports.migrated_video_upload import is_uuid
from gflow_cli.errors import NativeMediaMutationUnknownError


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
    owned: dict[str, dict[str, Any]] = {}
    for row in media:
        mid = row.get("media_id")
        if row.get("project_id") != project_id or not is_uuid(mid):
            continue
        if mid in owned:
            raise ValueError("Native media ownership is ambiguous")
        owned[str(mid)] = row
    if any(mid not in owned for mid in media_ids):
        raise ValueError("Every requested media must belong to the selected project")
    requested = set(media_ids)
    for mid in media_ids:
        row = owned[mid]
        siblings = row.get("batch_media_ids")
        if not isinstance(siblings, list) or not siblings:
            raise ValueError("Native batch membership is unavailable; refusing archive")
        siblings = cast(list[str], siblings)
        if (
            len(siblings) > 100
            or not all(is_uuid(item) for item in siblings)
            or len(set(siblings)) != len(siblings)
            or mid not in siblings
            or not is_uuid(row.get("workflow_id"))
            or row.get("archived") is not False
        ):
            raise ValueError("Native batch membership or active workflow is invalid")
        if set(siblings) - requested:
            raise ValueError("Native trash archives a batch; select every media in the batch")
        for sibling in siblings:
            other = owned.get(sibling)
            if (
                other is None
                or other.get("workflow_id") != row["workflow_id"]
                or other.get("archived") is not False
                or other.get("batch_media_ids") != siblings
            ):
                raise ValueError("Every batch sibling must be an active owned matching workflow")
    workflows = dict.fromkeys(owned[mid]["workflow_id"] for mid in media_ids)
    rows = [[workflow, None, None, [None, None, 1], project_id] for workflow in workflows]
    return [rows, [["metadata.archived"]]]


async def read_project_payload(page: Any, project_id: str) -> Any:
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
            length = response.headers.get("content-length")
            if length and int(length) > 2 * 1024 * 1024:
                reply.set_exception(ValueError("Native project response exceeds 2 MiB"))
                return
            text = await response.text()
            if len(text.encode("utf-8")) > 2 * 1024 * 1024:
                if not reply.done():
                    reply.set_exception(ValueError("Native project response exceeds 2 MiB"))
                return
        except Exception:
            return  # A previous navigation can abort a response body; it is not this read.
        try:
            for rpc, payload in parse_frames(text):
                if rpc == "Zzl0ze":
                    project_media(payload, project_id)
                    if not reply.done():
                        reply.set_result(payload)
        except Exception as exc:
            if not reply.done():
                reply.set_exception(exc)

    page.on("response", on_response)
    try:
        # A fresh project navigation ensures the SPA emits its authoritative timeline.
        await page.goto(f"https://flow.google.com/project/{project_id}")
        return list(await asyncio.wait_for(reply, timeout=30))
    finally:
        page.remove_listener("response", on_response)


async def read_project(page: Any, project_id: str) -> list[dict[str, Any]]:
    return project_media(await read_project_payload(page, project_id), project_id)


async def trash_media(page: Any, project_id: str, media_ids: list[str]) -> list[str]:
    media = await read_project(page, project_id)
    payload = trash_payload(media_ids, media, project_id)
    # Use the authenticated page's same-origin fetch; never persist or log CSRF/session data.
    acknowledged: set[str] = set()
    try:
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
    except asyncio.CancelledError as exc:
        vars(exc)["gflow_native_media_unknown"] = NativeMediaMutationUnknownError(
            operation="archive",
            phase="cancelled",
            project_id=project_id,
            pending_media_ids=tuple(media_ids),
        )
        raise
    except Exception:
        raise NativeMediaMutationUnknownError(
            operation="archive",
            phase="dispatch",
            project_id=project_id,
            pending_media_ids=tuple(media_ids),
        ) from None
    response = cast(dict[str, Any], response) if isinstance(response, dict) else {}
    if response.get("status") != 200 or not isinstance(response.get("text"), str):
        raise NativeMediaMutationUnknownError(
            operation="archive",
            phase="response",
            project_id=project_id,
            pending_media_ids=tuple(media_ids),
        ) from None
    try:
        frames = parse_frames(response["text"])
    except Exception:
        raise NativeMediaMutationUnknownError(
            operation="archive",
            phase="response",
            project_id=project_id,
            pending_media_ids=tuple(media_ids),
        ) from None
    expected = {row[0] for row in payload[0]}
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
        known = tuple(mid for mid in media_ids if owned_workflow(media, mid) in acknowledged)
        raise NativeMediaMutationUnknownError(
            operation="archive",
            phase="response",
            project_id=project_id,
            known_media_ids=known,
            pending_media_ids=tuple(mid for mid in media_ids if mid not in known),
        )
    return media_ids


def owned_workflow(media: list[dict[str, Any]], media_id: str) -> str:
    return str(next(row["workflow_id"] for row in media if row["media_id"] == media_id))
