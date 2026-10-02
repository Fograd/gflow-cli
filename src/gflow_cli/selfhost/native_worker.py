"""Private native resource worker. Arguments: VERB PROFILE JSON_PAYLOAD.

Paths are resolved and contained by the REST registry before dispatch. Each process
holds the normal profile lease; no shell evaluation or arbitrary remote URL is accepted.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

from gflow_cli import auth
from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_catalog import parse_native_characters, parse_native_voices
from gflow_cli.api.transports.migrated_characters import (
    CharacterBindingError,
    CharacterCreationError,
    CharacterDeletionError,
    CharacterUpdateError,
    mutate_character,
)
from gflow_cli.api.transports.migrated_projects import list_projects
from gflow_cli.api.transports.migrated_resources import (
    read_project,
    read_project_payload,
    trash_media,
)
from gflow_cli.api.transports.migrated_video_upload import UploadRightsRequiredError, upload_video
from gflow_cli.config import get_settings


async def execute(verb: str, profile: str, payload: dict[str, Any]) -> dict[str, Any]:
    if get_settings().flow_host == "labs.google":
        raise ValueError("Native resource operations require the migrated Flow host")
    project_id = "" if verb == "projects-list" else str(payload["project_id"])
    async with FlowApiClient(profile_dir=auth.profile_dir(profile), headless=False) as client:
        page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
        try:
            if verb == "projects-list":
                return {"status": "ok", **await list_projects(page, payload.get("cursor"))}
            if verb in {"character-create", "character-update", "character-delete"}:
                workflow_id = payload.get("workflow_id")
                verified_image = payload.get("image_reference_confirmed", False)
                if not isinstance(verified_image, bool):
                    raise ValueError("image_reference_confirmed must be a boolean")
                result = await mutate_character(
                    page,
                    project_id,
                    verb.removeprefix("character-"),
                    str(payload.get("entity_id", "")),
                    payload.get("display_name"),
                    payload.get("personality"),
                    workflow_id,
                    image_reference_confirmed=verified_image,
                    source_media_id=payload.get("media_id"),
                    second_media_id=payload.get("second_media_id"),
                    voice=payload.get("voice"),
                )
                return {"status": "ok", "project_id": project_id, **result}
            if verb in {"characters-list", "voice-presets"}:
                data = await read_project_payload(page, project_id)
                key = "characters" if verb == "characters-list" else "voices"
                rows = (
                    parse_native_characters(data, project_id)
                    if key == "characters"
                    else parse_native_voices(data)
                )
                return {"status": "ok", "project_id": project_id, key: rows}
            if verb == "upload-video":
                rights = payload.get("rights_confirmed", False)
                if not isinstance(rights, bool):
                    raise ValueError("rights_confirmed must be a boolean")
                media_id, caption = await upload_video(
                    page,
                    project_id,
                    Path(payload["path"]),
                    rights_confirmed=rights,
                )
                return {
                    "status": "ok",
                    "media_id": media_id,
                    "project_id": project_id,
                    "caption": caption,
                    "kind": "video",
                }
            if verb == "media-list":
                media = await read_project(page, project_id)
                return {"status": "ok", "project_id": project_id, "media": media}
            if verb == "media-delete":
                if not isinstance(payload["media_ids"], list):
                    raise ValueError("media_ids must be a list")
                ids = cast("list[Any]", payload["media_ids"])
                if not all(isinstance(mid, str) for mid in ids):
                    raise ValueError("media_ids must be a list of UUID strings")
                deleted = await trash_media(page, project_id, cast("list[str]", ids))
                return {
                    "status": "ok",
                    "project_id": project_id,
                    "deleted": deleted,
                    "operation": "archive",
                }
            raise ValueError("Unsupported native worker operation")
        finally:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: native_worker VERB PROFILE JSON_PAYLOAD")
    data = json.loads(sys.argv[3])
    if not isinstance(data, dict):
        raise SystemExit("Worker payload must be an object")
    try:
        result = asyncio.run(execute(sys.argv[1], sys.argv[2], cast("dict[str, Any]", data)))
    except CharacterBindingError as exc:
        result = {
            "status": "error",
            "code": "character_binding_outcome_unknown",
            "createdCharacterRef": exc.entity_id,
            "project_id": cast("dict[str, Any]", data).get("project_id"),
            "detail": "Character created but image binding failed; inspect before retrying",
        }
    except CharacterCreationError:
        result = {
            "status": "error",
            "code": "character_create_outcome_unknown",
            "project_id": cast("dict[str, Any]", data).get("project_id"),
            "detail": "Creation outcome unknown; inspect before retrying",
        }
    except CharacterUpdateError as exc:
        result = {
            "status": "error",
            "code": "character_update_outcome_unknown",
            "characterRef": exc.entity_id,
            "project_id": cast("dict[str, Any]", data).get("project_id"),
            "detail": "Metadata update outcome unknown; inspect before retrying",
        }
    except CharacterDeletionError as exc:
        result = {
            "status": "error",
            "code": "character_delete_outcome_unknown",
            "characterRef": exc.entity_id,
            "project_id": cast("dict[str, Any]", data).get("project_id"),
            "detail": "Character deletion outcome unknown; inspect before retrying",
        }
    except UploadRightsRequiredError:
        result = {
            "status": "error",
            "code": "upload_rights_required",
            "detail": "Affirm upload ownership with X-Flow-Rights-Confirmed: true or confirm "
            "once in the logged-in browser; no video ingestion was submitted",
        }
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
