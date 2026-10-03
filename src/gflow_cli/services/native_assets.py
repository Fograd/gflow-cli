"""Portable selected-profile native media lookup/download adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.native_asset_lookup import NativeAsset, NativeAudioAsset
from gflow_cli.config import get_settings


def asset_payload(asset: NativeAsset | NativeAudioAsset) -> dict[str, Any]:
    """Explicit confidential response; never use as a routine event/history value."""
    return {
        "mediaGenerationId": asset.media_id,
        "projectId": asset.project_id,
        "workflowId": asset.workflow_id,
        "kind": asset.kind,
        "url": asset.url,
        "width": asset.width,
        "height": asset.height,
    }


async def read_asset(
    profile: str, project: str, media: str, out_dir: Path | None = None
) -> dict[str, Any]:
    settings = get_settings()
    async with FlowApiClient(
        profile_dir=settings.profile_subdir(profile), headless=settings.headless
    ) as client:
        if out_dir is None:
            return asset_payload(await client.get_native_asset(project, media))
        result = await client.download_native_asset(project, media, out_dir)
        return {
            "mediaGenerationId": result.media_id,
            "projectId": result.project_id,
            "workflowId": result.workflow_id,
            "kind": result.kind,
            "path": str(result.path),
            "bytes": result.bytes,
            "sha256": result.sha256,
            "mimeType": result.mime_type,
            "width": result.width,
            "height": result.height,
        }
