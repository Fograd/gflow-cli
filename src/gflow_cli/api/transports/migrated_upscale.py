"""Drive Flow's migrated ``flow.google.com`` editor to upscale generated images.

Google moved Flow from ``labs.google`` onto ``flow.google.com`` (#639). On that frontend,
upscaling is triggered through the image detail view download menu, which calls the
``SPrCad`` RPC over ``batchexecute`` and returns base64 image bytes directly.
"""

from __future__ import annotations

import asyncio
import base64
import json
from contextvars import copy_context
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs

import structlog
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.image_upscale import TargetResolution
from gflow_cli.api.native_captcha import native_captcha_active, native_captcha_outcome
from gflow_cli.api.recaptcha import TokenMinter
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors, rpc_reply_frame_count

# Shared typed-refusal decoder at the native transport boundary.
from gflow_cli.api.transports.migrated_composer import (
    MIGRATED_PROJECT_URL,
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_upscale_overrides import UpscaleOverride
from gflow_cli.api.transports.native_asset_lookup import lookup_asset
from gflow_cli.errors import (
    TransportTimeoutError,
    UiSelectorDriftError,
    UpscaleUnavailableError,
    WireFormatError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import Page, Response

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

    2K is numeric value 1 on the measured wire. The Pro account cannot submit
    4K, so its numeric value remains unmeasured here; media and project still
    bind that request to this operation.
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
        if target_resolution is TargetResolution.RES_2K and args[1] != 1:
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
    project_url = MIGRATED_PROJECT_URL.format(project_id=project_id)
    override = None
    context = copy_context()
    if native_captcha_active():
        if target_resolution is not TargetResolution.RES_2K:
            raise UpscaleUnavailableError(
                detail="Explicit CAPTCHA override currently supports measured 2K upscale only",
                route="image_upscale",
                status=501,
            )
        await page.goto(project_url, wait_until="domcontentloaded")
        owned = await lookup_asset(page, project_id=project_id, media_id=media_id)
        if owned.media_id != media_id or owned.project_id != project_id or owned.kind != "image":
            raise WireFormatError(
                detail="Explicit image upscale requires fresh selected-project owned image proof",
                route="image_upscale",
            )
        token = await TokenMinter(page).mint("IMAGE_GENERATION")
        override = UpscaleOverride(project=project_id, media=media_id, token=token)
    log.info("migrated_upscale.navigate", project_id=project_id, media_id=media_id)
    # The project gallery virtualises old tiles out of the DOM. Opening a
    # validated detail URL works independently of gallery size and scroll state.
    detail_url = f"{project_url}/edit/{media_id}"
    await page.goto(detail_url, wait_until="domcontentloaded")

    # Click the download button in the image detail viewer (exact icon match)
    try:
        download_btn = await page.wait_for_selector(
            'button:has(mat-icon:text-is("download")), '
            'button:has(.google-symbols:text-is("download"))',
            timeout=15_000,
        )
    except PlaywrightTimeoutError as exc:
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

    # Check 2K and 4K menu items availability
    scale_label = "4K" if target_resolution is TargetResolution.RES_4K else "2K"
    btn_target = None
    try:
        btn_target = await page.wait_for_selector(
            f'[role="menuitem"]:has-text("{scale_label}")', timeout=5000
        )
    except PlaywrightTimeoutError as exc:
        raise UiSelectorDriftError(
            detail=f"migrated upscale: menu item for {scale_label} was not found in the menu",
            route="image_upscale",
        ) from exc

    if btn_target is None:
        raise UiSelectorDriftError(
            detail=f"migrated upscale: menu item for {scale_label} was not found in the menu",
            route="image_upscale",
        )

    is_disabled = await btn_target.is_disabled() or (
        await btn_target.get_attribute("aria-disabled") == "true"
    )
    if is_disabled:
        if target_resolution is TargetResolution.RES_4K:
            raise UpscaleUnavailableError(
                detail=(
                    "4K upscale requires a Flow Ultra subscription. "
                    "Your account supports up to 2K (use --scale 2k)."
                ),
                route="upsampleImage",
                status=403,
            )
        raise UpscaleUnavailableError(
            detail=f"{scale_label} upscale is not available on this account.",
            route="upsampleImage",
            status=403,
        )

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
