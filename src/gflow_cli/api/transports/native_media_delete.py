"""Source-defined permanent individual media deletion, distinct from archive."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from gflow_cli.api.native_delete_receipts import DeleteReceipts

from gflow_cli.api.transports.migrated_rpc import NativeMetadataRpcError, native_rpc
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import NativeMediaMutationUnknownError


def validate_delete(
    project_id: str, media_ids: object, confirm_delete: object
) -> tuple[str, tuple[str, ...]]:
    if confirm_delete is not True:
        raise ValueError("Permanent media deletion requires explicit confirmation")
    project = validate_identifier(project_id)
    if not isinstance(media_ids, (list, tuple)):
        raise ValueError("Media deletion requires 1 to 100 distinct UUIDs")
    identifiers = cast(list[Any] | tuple[Any, ...], media_ids)
    if not 1 <= len(identifiers) <= 100:
        raise ValueError("Media deletion requires 1 to 100 distinct UUIDs")
    normalized = tuple(validate_identifier(value) for value in identifiers)
    if len(set(normalized)) != len(normalized):
        raise ValueError("Media deletion requires distinct UUIDs")
    return project, normalized


def owned_media(payload: Any, project: str, identifier: str) -> str:
    if not isinstance(payload, list):
        raise ValueError("Media deletion ownership response is unavailable")
    row = cast(list[Any], payload)
    if len(row) < 7 or row[0] != identifier or row[1] != project:
        raise ValueError("Media deletion ownership does not match the selected project")
    workflow = validate_identifier(row[2])
    arms = [row[i] for i in (6, 7, 10) if len(row) > i and row[i] is not None]
    if len(arms) != 1 or not isinstance(arms[0], list) or not arms[0]:
        raise ValueError("Media deletion requires a known unambiguous media type")
    return workflow


async def delete_individual_media(
    page: Any,
    project_id: str,
    media_ids: object,
    confirm_delete: object = False,
    *,
    receipts: DeleteReceipts | None = None,
) -> dict[str, Any]:
    project, identifiers = validate_delete(project_id, media_ids, confirm_delete)
    if str(page.url).rstrip("/") != "https://flow.google.com/project/" + project:
        await page.goto("https://flow.google.com/project/" + project, wait_until="domcontentloaded")
    await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=15000)
    present: list[str] = []
    already: list[str] = []
    kinds: dict[str, str] = {}
    async with asyncio.timeout(120):
        for identifier in identifiers:
            try:
                row = await native_rpc(
                    page, "as29s", [identifier], "/project/" + project, require_single=True
                )
            except NativeMetadataRpcError as error:
                if (
                    error.rpcid != "as29s"
                    or type(error.code) is not int
                    or error.code != 5
                    or receipts is None
                    or receipts.kind(identifier) is None
                ):
                    raise ValueError(
                        "Missing media has no confirmed scoped deletion receipt"
                    ) from None
                already.append(identifier)
                continue
            owned_media(row, project, identifier)
            kinds[identifier] = next(
                kind
                for index, kind in ((6, "image"), (7, "video"), (10, "audio"))
                if len(row) > index and row[index] is not None
            )
            present.append(identifier)
    if not present:
        return {
            "project_id": project,
            "deleted": list(identifiers),
            "newly_deleted": [],
            "already_deleted": already,
            "receipt_persisted": True,
            "operation": "delete",
            "scope": "native permanent individual media deletion",
        }
    # Intentionally omit workflow field2. Siblings and confirmed-gone IDs are never requested.
    payload = [None, None, project, None, None, None, present]
    try:
        reply = await native_rpc(
            page, "cz8Z4b", payload, "/project/" + project, require_single=True
        )
        if reply != []:
            raise ValueError("Permanent media deletion acknowledgement is unavailable")
    except BaseException as error:
        typed = NativeMediaMutationUnknownError(
            operation="delete",
            phase="cancelled" if isinstance(error, asyncio.CancelledError) else "response",
            project_id=project,
            pending_media_ids=identifiers,
        )
        if isinstance(error, asyncio.CancelledError):
            vars(error)["gflow_native_media_unknown"] = typed
            raise
        if not isinstance(error, Exception):
            raise
        raise typed from None
    persisted = receipts is not None
    if receipts is not None:
        try:
            for identifier in present:
                receipts.record(identifier, kinds[identifier])
        except Exception:
            # Google already acknowledged. Report known success, never invite mutation retry.
            persisted = False
    return {
        "project_id": project,
        "deleted": list(identifiers),
        "newly_deleted": present,
        "already_deleted": already,
        "receipt_persisted": persisted,
        "operation": "delete",
        "scope": "native permanent individual media deletion",
    }
