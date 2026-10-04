"""Drive Flow's migrated ``flow.google.com`` editor to upscale generated images.

Google moved Flow from ``labs.google`` onto ``flow.google.com`` (#639). On that frontend,
upscaling is triggered through the image detail view download menu, which calls the
``SPrCad`` RPC over ``batchexecute`` and returns base64 image bytes directly.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from contextvars import copy_context
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs

import structlog

from gflow_cli.api._engine import engine_timeout_errors
from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.api.native_captcha import native_captcha_active, native_captcha_outcome
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.api.transports.batchexecute import (
    parse_frames,
    public_quota_refusal,
    rpc_errors,
    rpc_reply_frame_count,
)

# Shared typed-refusal decoder at the native transport boundary.
from gflow_cli.api.transports.migrated_composer import (
    MIGRATED_PROJECT_URL,
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_upscale_overrides import (
    UpscaleOverride,
    native_upscale_enum,
)
from gflow_cli.api.transports.native_asset_lookup import lookup_asset
from gflow_cli.errors import (
    ConfigurationError,
    NativeQuotaError,
    TransportTimeoutError,
    UiSelectorDriftError,
    UpscaleUnavailableError,
    WireFormatError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import ElementHandle, Page, Response

log = structlog.get_logger(__name__)

UPSCALE_RPCID = "SPrCad"
_DEFAULT_TIMEOUT_S = 90.0
# Bound allocation before base64 decoding, matching the legacy image path.
MAX_IMAGE_B64_LEN = 50 * 1024 * 1024

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8"


def is_png_or_jpeg(data: bytes) -> bool:
    """True if data begins with a PNG or JPEG magic-byte signature."""
    return data.startswith(_PNG_MAGIC) or data.startswith(_JPEG_MAGIC)


def matches_upscale_request(
    body: str | None, *, media_id: str, project_id: str, target_resolution: TargetResolution
) -> bool:
    """Correlate the observed SPrCad request before accepting its response.

    Google's current frontend maps image 2K/4K to numeric 1/2. Native image
    and selected project bind the synchronous in-place output to this operation.
    """
    if not isinstance(body, str):
        return False
    try:
        frames = json.loads(parse_qs(body)["f.req"][0])
        frame = frames[0][0]
        if frame[0] != UPSCALE_RPCID:
            return False
        raw_args: Any = json.loads(frame[1])
        if not isinstance(raw_args, list):
            return False
        args = cast("list[Any]", raw_args)
        if len(args) < 3 or args[0] != media_id:
            return False
        if type(args[1]) is not int or args[1] != native_upscale_enum(target_resolution):
            return False
        pending: list[Any] = [args[2]]
        while pending:
            value = pending.pop()
            if value == project_id:
                return True
            if isinstance(value, list):
                pending.extend(cast("list[Any]", value))
            elif isinstance(value, dict):
                pending.extend(cast("dict[str, Any]", value).values())
        return False
    except (KeyError, IndexError, TypeError, ValueError):
        return False


async def _open_upscale_menu(page: Page, *, download_button: ElementHandle | None = None) -> None:
    """Read the current exact detail-menu availability; never dispatch or mint."""
    # Click the download button in the image detail viewer (exact icon match)
    download_btn = download_button
    if download_btn is None:
        try:
            download_btn = await page.wait_for_selector(
                'button:has(mat-icon:text-is("download")), '
                'button:has(.google-symbols:text-is("download"))',
                timeout=15_000,
            )
        except engine_timeout_errors() as exc:
            raise WireFormatError(
                detail="Download button not found in image detail view",
                route="image_upscale",
            ) from exc
    if not download_btn:
        raise WireFormatError(
            detail="Download button not found in image detail view",
            route="image_upscale",
        )
    await download_btn.click()
    await page.wait_for_timeout(500)


async def _upscale_menu(page: Page, target_resolution: TargetResolution) -> ElementHandle:
    """Strict paid-operation guard; menu opening is shared with discovery."""
    await _open_upscale_menu(page)
    # Check 2K and 4K menu items availability
    scale_label = "4K" if target_resolution is TargetResolution.RES_4K else "2K"
    btn_target = None
    try:
        btn_target = await page.wait_for_selector(
            f'[role="menuitem"]:has-text("{scale_label}")', timeout=5000
        )
    except engine_timeout_errors() as exc:
        raise UiSelectorDriftError(
            detail=f"migrated upscale: menu item for {scale_label} was not found in the menu",
            route="image_upscale",
        ) from exc

    if btn_target is None:
        raise UiSelectorDriftError(
            detail=f"migrated upscale: menu item for {scale_label} was not found in the menu",
            route="image_upscale",
        )

    is_disabled = await _upscale_item_disabled(btn_target)
    if is_disabled:
        raise UpscaleUnavailableError(
            detail=f"{scale_label} upscale is disabled in this image's current download menu.",
            route="upsampleImage",
            status=403,
        )

    return btn_target


_CAPABILITY_SCOPE = "fresh owned image detail-menu observation"
_DOWNLOAD_SELECTOR = (
    'button:has(mat-icon:text-is("download")), button:has(.google-symbols:text-is("download"))'
)
_CAPABILITY_REASONS = {
    "enabled_menu_item",
    "disabled_menu_item",
    "resolution_unobserved",
    "resolution_ambiguous",
    "menu_unobserved",
    "menu_ambiguous",
    "menu_context_unverified",
    "download_trigger_unobserved",
    "download_trigger_ambiguous",
    "detail_context_unverified",
    "observation_timeout",
}


def _capability(resolution: str, state: str, reason: str) -> dict[str, Any]:
    return {
        "resolution": resolution,
        "status": state,
        "available": True if state == "available" else False if state == "disabled" else None,
        "reason": reason,
    }


def _unknown_capabilities(reason: str) -> list[dict[str, Any]]:
    return [_capability(resolution, "unknown", reason) for resolution in ("2k", "4k")]


def validate_upscale_capabilities(value: Any, *, project: str, media: str) -> dict[str, Any]:
    """Allow only the correlated, URL-free observation envelope from a read worker."""
    if not isinstance(value, dict):
        raise ValueError("Image capability scope is unavailable")
    payload = cast("dict[str, Any]", value)
    if (
        payload.get("project_id") != project
        or payload.get("media_id") != media
        or payload.get("scope") != _CAPABILITY_SCOPE
    ):
        raise ValueError("Image capability scope is unavailable")
    raw_rows = payload.get("capabilities")
    if not isinstance(raw_rows, list):
        raise ValueError("Image capability resolutions are unavailable")
    rows = cast("list[Any]", raw_rows)
    if len(rows) != 2:
        raise ValueError("Image capability resolutions are unavailable")
    for resolution, raw in zip(("2k", "4k"), rows, strict=True):
        if not isinstance(raw, dict):
            raise ValueError("Image capability observation is invalid")
        row = cast("dict[str, Any]", raw)
        if (
            set(row) != {"resolution", "status", "available", "reason"}
            or row["resolution"] != resolution
            or not isinstance(row["status"], str)
            or row["status"] not in {"available", "disabled", "unknown"}
            or not isinstance(row["reason"], str)
            or row["reason"] not in _CAPABILITY_REASONS
        ):
            raise ValueError("Image capability observation is invalid")
        expected = (
            True if row["status"] == "available" else False if row["status"] == "disabled" else None
        )
        if row["available"] is not expected:
            raise ValueError("Image capability availability is inconsistent")
        if (
            row["status"] != "unknown"
            and row["reason"]
            != {"available": "enabled_menu_item", "disabled": "disabled_menu_item"}[row["status"]]
        ):
            raise ValueError("Image capability reason is inconsistent")
        if row["status"] == "unknown" and row["reason"] in {
            "enabled_menu_item",
            "disabled_menu_item",
        }:
            raise ValueError("Unknown image capability must retain uncertainty")
    return {
        "project_id": project,
        "media_id": media,
        "capabilities": rows,
        "scope": _CAPABILITY_SCOPE,
    }


async def _upscale_item_disabled(item: Any) -> bool:
    return await item.is_disabled() or await item.get_attribute("aria-disabled") == "true"


async def inspect_upscale_menu(page: Page) -> list[dict[str, Any]]:
    """Open one unique download menu; never select a resolution or mint a token."""
    try:
        await page.wait_for_selector(_DOWNLOAD_SELECTOR, state="visible", timeout=5000)
        triggers = [
            item
            for item in await page.query_selector_all(_DOWNLOAD_SELECTOR)
            if await item.is_visible()
        ]
        if len(triggers) != 1:
            return _unknown_capabilities(
                "download_trigger_unobserved" if not triggers else "download_trigger_ambiguous"
            )
        if any(
            [await menu.is_visible() for menu in await page.query_selector_all('[role="menu"]')]
        ):
            return _unknown_capabilities("menu_context_unverified")
        await _open_upscale_menu(page, download_button=triggers[0])
        await page.wait_for_selector('[role="menu"]', state="visible", timeout=5000)
        menus = [
            item
            for item in await page.query_selector_all('[role="menu"]')
            if await item.is_visible()
        ]
        if len(menus) != 1:
            return _unknown_capabilities("menu_unobserved" if not menus else "menu_ambiguous")
        items: dict[str, list[Any]] = {"2k": [], "4k": []}
        for item in await menus[0].query_selector_all('[role="menuitem"]'):
            if not await item.is_visible():
                continue
            labels = re.findall(
                r"(?<![A-Za-z0-9])([24])\s*K(?![A-Za-z0-9])", await item.inner_text(), re.IGNORECASE
            )
            if len(labels) == 1:
                items[labels[0] + "k"].append(item)
            elif labels:
                for label in set(labels):
                    items[label + "k"].extend((item, item))
        result: list[dict[str, Any]] = []
        for resolution, matches in items.items():
            if len(matches) != 1:
                result.append(
                    _capability(
                        resolution,
                        "unknown",
                        "resolution_unobserved" if not matches else "resolution_ambiguous",
                    )
                )
                continue
            disabled = await _upscale_item_disabled(matches[0])
            result.append(
                _capability(
                    resolution,
                    "disabled" if disabled else "available",
                    "disabled_menu_item" if disabled else "enabled_menu_item",
                )
            )
        return result
    except (WireFormatError, *engine_timeout_errors()):
        return _unknown_capabilities("observation_timeout")


async def read_image_upscale_capabilities(
    client: Any, *, project_id: str, media_id: str
) -> dict[str, Any]:
    """Bounded exact-owned-image read. UI uncertainty is distinct from ownership failure."""
    from gflow_cli.api.native_extension import _uuid  # pyright: ignore[reportPrivateUsage]

    project, media = _uuid(project_id), _uuid(media_id)
    page = None
    owned = False
    result = _unknown_capabilities("observation_timeout")
    project_url = MIGRATED_PROJECT_URL.format(project_id=project)
    detail_url = f"{project_url}/edit/{media}"
    try:
        try:
            async with asyncio.timeout(45):
                page = await client._checkout_page()
                await page.goto(project_url, wait_until="domcontentloaded", timeout=15000)
                asset = await lookup_asset(page, project_id=project, media_id=media)
                if asset.media_id != media or asset.project_id != project or asset.kind != "image":
                    raise ConfigurationError(
                        detail="Image capability discovery requires an exact owned image"
                    )
                owned = True
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                if page.url.split("?")[0].split("#")[0] != detail_url:
                    result = _unknown_capabilities("detail_context_unverified")
                else:
                    result = await inspect_upscale_menu(page)
                    if page.url.split("?")[0].split("#")[0] != detail_url:
                        result = _unknown_capabilities("detail_context_unverified")
        except (TimeoutError, *engine_timeout_errors()) as exc:
            if not owned:
                raise TransportTimeoutError(
                    detail="Image capability ownership verification timed out",
                    route="image_upscale_capabilities",
                ) from exc
    finally:
        if page is not None:
            try:
                async with asyncio.timeout(1):
                    await page.keyboard.press("Escape")
            except (TimeoutError, *engine_timeout_errors()):
                pass
            finally:
                client._checkin_page(page)
    return {
        "project_id": project,
        "media_id": media,
        "capabilities": result,
        "scope": _CAPABILITY_SCOPE,
    }


async def upscale_image_migrated(
    page: Page,
    *,
    project_id: str,
    media_id: str,
    target_resolution: TargetResolution,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> bytes:
    """Upscale an image on the migrated ``flow.google.com`` frontend.

    Navigates directly to the image detail view, opens
    the download menu, checks whether the requested scale is available on the
    current account tier, triggers the upscale, and decodes the resulting
    ``SPrCad`` payload into raw image bytes.

    Returns:
        Raw decoded JPEG/PNG bytes.
    """
    native_upscale_enum(target_resolution)  # refuse unknown input before navigation or mint
    project_url = MIGRATED_PROJECT_URL.format(project_id=project_id)
    detail_url = f"{project_url}/edit/{media_id}"
    override = None
    context = copy_context()
    if native_captcha_active():
        await page.goto(project_url, wait_until="domcontentloaded")
        owned = await lookup_asset(page, project_id=project_id, media_id=media_id)
        if owned.media_id != media_id or owned.project_id != project_id or owned.kind != "image":
            raise WireFormatError(
                detail="Explicit image upscale requires fresh selected-project owned image proof",
                route="image_upscale",
            )
        if target_resolution is TargetResolution.RES_4K:
            # A source-proven enum does not establish this account's entitlement.
            # Probe fresh UI availability before paid mint, then recheck after mint.
            await page.goto(detail_url, wait_until="domcontentloaded")
            await _upscale_menu(page, target_resolution)
            await page.goto(project_url, wait_until="domcontentloaded")
        token = await TokenMinter(page).mint("IMAGE_GENERATION")
        override = UpscaleOverride(
            project=project_id, media=media_id, token=token, target_resolution=target_resolution
        )
    log.info("migrated_upscale.navigate", project_id=project_id, media_id=media_id)
    # The project gallery virtualises old tiles out of the DOM. Opening a
    # validated detail URL works independently of gallery size and scroll state.
    await page.goto(detail_url, wait_until="domcontentloaded")

    btn_target = await _upscale_menu(page, target_resolution)

    loop = asyncio.get_running_loop()
    found_b64: asyncio.Future[str] = loop.create_future()

    async def on_response(response: Response) -> None:
        if override is not None and (
            not override.dispatched or response.request is not override.request
        ):
            return
        if override is not None or (
            "batchexecute" in response.url and UPSCALE_RPCID in response.url
        ):
            if not matches_upscale_request(
                response.request.post_data,
                media_id=media_id,
                project_id=project_id,
                target_resolution=target_resolution,
            ):
                return
            try:
                text = await response.text()
                if override is not None and rpc_reply_frame_count(text, UPSCALE_RPCID) != 1:
                    if not found_b64.done():
                        found_b64.set_exception(
                            WireFormatError(
                                detail="Image upscale reply requires exactly one correlated frame",
                                route="image_upscale",
                            )
                        )
                    return
                quota = public_quota_refusal(text, (UPSCALE_RPCID,))
                if quota is not None:
                    if not found_b64.done():
                        if override is not None:
                            context.run(native_captcha_outcome, "rejected")
                        found_b64.set_exception(
                            NativeQuotaError(
                                quota[2],
                                route=f"batchexecute:{UPSCALE_RPCID}",
                                operation="images/upscale",
                            )
                        )
                    return
                errors = rpc_errors(text)
                if any(e.rpcid == UPSCALE_RPCID for e in errors):
                    err = next(e for e in errors if e.rpcid == UPSCALE_RPCID)
                    if override is not None:
                        same_rpc_payload = any(
                            rpcid == UPSCALE_RPCID for rpcid, _ in parse_frames(text)
                        )
                        refusal = _submit_refusal(text, (UPSCALE_RPCID,))
                        if refusal is not None and not same_rpc_payload:
                            context.run(native_captcha_outcome, "rejected")
                            if not found_b64.done():
                                found_b64.set_exception(refusal)
                            return
                    if not found_b64.done():
                        found_b64.set_exception(
                            WireFormatError(
                                detail=f"SPrCad RPC refused: code={err.code} reasons={err.reasons}",
                                route="image_upscale",
                            )
                        )
                    return
                frames = parse_frames(text)
                for rpcid, payload in frames:
                    if rpcid == UPSCALE_RPCID and isinstance(payload, list):
                        items = cast("list[Any]", payload)
                        if len(items) >= 2:
                            b64_val = items[1]
                            if isinstance(b64_val, str) and len(b64_val) > 0:
                                if not found_b64.done():
                                    if override is not None:
                                        context.run(native_captcha_outcome, "accepted")
                                    found_b64.set_result(b64_val)
            except Exception as exc:  # noqa: BLE001
                log.warning("migrated_upscale.parse_error", error_type=type(exc).__name__)
                if not found_b64.done():
                    found_b64.set_exception(
                        WireFormatError(
                            detail="Failed to parse SPrCad response",
                            route="image_upscale",
                        )
                    )

    async def guard(route: Any, request: Any) -> None:
        assert override is not None
        try:
            await override.guard(route, request)
        except Exception as exc:
            if not found_b64.done():
                found_b64.set_exception(exc)

    route_pattern = "**/batchexecute*"
    page.on("response", on_response)
    try:
        if override is not None:
            await page.route(route_pattern, guard)
        # Override anchor click and preserve original to restore later
        await page.evaluate("""() => {
            window._origAnchorClick = HTMLAnchorElement.prototype.click;
            HTMLAnchorElement.prototype.click = function() {};
        }""")
        await btn_target.click()

        try:
            b64_data = await asyncio.wait_for(found_b64, timeout=timeout_s)
        except TimeoutError as exc:
            raise TransportTimeoutError(
                detail=(
                    f"Timed out after {timeout_s}s waiting for {UPSCALE_RPCID} response from Flow"
                ),
                route="image_upscale",
            ) from exc
    finally:
        if override is not None and override.dispatched:
            context.run(native_captcha_outcome, "unknown")
        page.remove_listener("response", on_response)
        if override is not None:
            try:
                await page.unroute(route_pattern, guard)
            except Exception as exc:  # noqa: BLE001
                log.warning("migrated_upscale.unroute_error", error_type=type(exc).__name__)
            finally:
                override.token = ""
        try:
            await page.evaluate("""() => {
                if (window._origAnchorClick) {
                    HTMLAnchorElement.prototype.click = window._origAnchorClick;
                    delete window._origAnchorClick;
                }
            }""")
        except Exception:  # noqa: BLE001
            pass

    if len(b64_data) > MAX_IMAGE_B64_LEN:
        raise WireFormatError(
            detail="upscaled image exceeds the encoded payload size cap",
            route="upsampleImage",
        )
    try:
        image_bytes = base64.b64decode(b64_data, validate=True)
    except ValueError as exc:
        raise WireFormatError(
            detail="upsampleImage returned undecodable image data",
            route="upsampleImage",
        ) from exc

    if not is_png_or_jpeg(image_bytes):
        raise WireFormatError(
            detail="upscaled output is not a valid PNG/JPEG",
            route="upsampleImage",
        )

    log.info(
        "migrated_upscale.completed",
        media_id=media_id,
        resolution=target_resolution.name,
        bytes=len(image_bytes),
    )
    return image_bytes
