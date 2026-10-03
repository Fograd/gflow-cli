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
)
from gflow_cli.api.transports.migrated_video_upload import UploadRightsRequiredError
from gflow_cli.config import get_settings
from gflow_cli.errors import NativeMediaMutationUnknownError


async def execute(verb: str, profile: str, payload: dict[str, Any]) -> dict[str, Any]:
    if get_settings().flow_host == "labs.google":
        raise ValueError("Native resource operations require the migrated Flow host")
    if verb == "session-health":
        from gflow_cli.selfhost.session_health import probe_project_access

        return {
            "status": "ok",
            "sessionHealth": await probe_project_access(profile, str(payload["project_id"])),
        }
    project_id = "" if verb == "projects-list" else str(payload["project_id"])
    if verb == "upload-video":
        from gflow_cli.api.native_media import upload_snapshot_context, validate_upload

        project = validate_upload(project_id, payload.get("rights_confirmed", False))
        result: dict[str, Any] = {}
        from gflow_cli.services.native_media import upload_private_snapshot

        with upload_snapshot_context(
            Path(payload["path"]), project=project, rights_confirmed=True, outcome=result
        ) as private:
            result.update(await upload_private_snapshot(profile, project, private))
        return {"status": "ok", **result, "kind": "video"}
    if verb == "media-delete":
        from gflow_cli.api.native_media import validate_archive

        project, identifiers = validate_archive(project_id, payload.get("media_ids"), True)
        from gflow_cli.services.native_media import archive_media

        result = await archive_media(profile, project, identifiers)
        return {
            "status": "ok",
            **result,
            "deleted": result["archived_media_ids"],
            "operation": "archive",
        }
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
            if verb == "media-list":
                media = await read_project(page, project_id)
                return {"status": "ok", "project_id": project_id, "media": media}
            raise ValueError("Unsupported native worker operation")
        finally:
            client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: native_worker VERB PROFILE JSON_PAYLOAD")
    data = json.loads(sys.argv[3])
    if not isinstance(data, dict):
        raise SystemExit("Worker payload must be an object")
    exit_code = 0
    try:
        result = asyncio.run(execute(sys.argv[1], sys.argv[2], cast("dict[str, Any]", data)))
    except NativeMediaMutationUnknownError as exc:
        exit_code = 40
        result = {
            "status": "error",
            "code": "native_media_mutation_outcome_unknown",
            "error": {
                **exc.to_problem_details(),
                "class": type(exc).__name__,
                "exit_code": 40,
                "retryable": False,
            },
        }
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
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
