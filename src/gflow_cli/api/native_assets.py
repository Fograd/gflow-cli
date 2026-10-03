"""Selected-profile native asset reads; no synthetic local catalog records."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from gflow_cli.api.transports.native_asset_download import DownloadedNativeAsset, download_asset
from gflow_cli.api.transports.native_asset_lookup import NativeAsset, lookup_asset
from gflow_cli.api.transports.native_voices import validate_identifier
from gflow_cli.errors import ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient


async def get_native_asset(client: FlowApiClient, project_id: str, media_id: str) -> NativeAsset:
    try:
        project, media = validate_identifier(project_id), validate_identifier(media_id)
    except ValueError:
        raise ConfigurationError(
            detail="Native asset lookup requires project and media UUIDs"
        ) from None
    if client.settings.flow_host == "labs.google":
        raise ConfigurationError(detail="Native asset lookup requires the migrated Flow host")
    try:
        async with asyncio.timeout(90):
            page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
            try:
                return await lookup_asset(page, project_id=project, media_id=media)
            finally:
                primary = sys.exception()
                try:
                    client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
                except BaseException:
                    if primary is None:
                        raise
                    primary.add_note("Native asset browser checkin remains incomplete")
    except (ValueError, TimeoutError):
        raise WireFormatError(
            detail="Native asset could not be resolved in the selected project",
            route="assets.native",
            remediation_hint=(
                "Check the selected account, project and typed native media UUID. "
                "No generation or mutation was attempted."
            ),
        ) from None


async def download_native_asset(
    client: FlowApiClient, project_id: str, media_id: str, out_dir: Path
) -> DownloadedNativeAsset:
    asset = await get_native_asset(client, project_id, media_id)
    try:
        return await download_asset(asset, out_dir)
    except FileExistsError:
        raise ConfigurationError(
            detail="Native media output already exists; choose another output directory"
        ) from None
    except (ValueError, TimeoutError, OSError):
        raise WireFormatError(
            detail="Native asset download failed content validation or its time/byte budget",
            route="assets.native.download",
            remediation_hint=(
                "Retry lookup to obtain fresh media metadata. "
                "This does not generate or upscale media."
            ),
        ) from None
