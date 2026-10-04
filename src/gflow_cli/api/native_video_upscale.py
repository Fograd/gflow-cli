"""Native p0UkFb resolution promotion, separate from existing media exports.

Current source-derived contract; accepted output dimensions remain R12 proof.
"""

from __future__ import annotations

# Internal helpers shared across the native RPC adapter boundary.
# pyright: reportPrivateUsage=false, reportUnnecessaryIsInstance=false
import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from gflow_cli.api._engine import page_owned_evaluate_kwargs
from gflow_cli.api.native_captcha import native_captcha_outcome, native_captcha_submission
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.native_extension import (
    _NATIVE_FETCH,
    NativeExtensionStarted,
    NativeExtensionUnknownError,
    _read_native,
    _uuid,
    assigned_id,
    parse_extension_models,
    wait_native_extension,
)
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.api.transports.migrated_composer import _submit_refusal
from gflow_cli.api.transports.migrated_resources import project_media, read_project_payload
from gflow_cli.api.transports.migrated_rpc import native_rpc
from gflow_cli.errors import (
    ConfigurationError,
    ContentPolicyError,
    NativeQuotaError,
    WafRejectionError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from gflow_cli.api.client import FlowApiClient
RPC = "p0UkFb"
TARGETS = {"720p": (1, 21), "1080p": (2, 15), "4k": (3, 16)}


class NativeVideoUpscaleUnknownError(NativeExtensionUnknownError):
    problem_type = "https://gflow-cli.dev/errors/native-video-upscale-unknown"
    title = "Native video promotion outcome unknown"

    def __init__(self, started: NativeExtensionStarted) -> None:
        super().__init__(started)
        self.route = "video.upscale.native"


@dataclass(frozen=True)
class NativePromotionStarted(NativeExtensionStarted):
    source_workflow_id: str = ""
    target_resolution: str = "1080p"


def new_promotion_started(
    project: str, media: str, workflow: str, resolution: str = "1080p"
) -> NativePromotionStarted:
    project, media, workflow = _uuid(project), _uuid(media), _uuid(workflow)
    if (
        len({project, media, workflow}) != 3
        or not isinstance(resolution, str)
        or resolution not in TARGETS
    ):
        raise ConfigurationError(
            detail="Native promotion requires distinct source identities and a supported target"
        )
    seed = str(uuid4())
    return NativePromotionStarted(
        project, media, (assigned_id(seed),), (workflow,), (seed,), (), workflow, resolution
    )


def promotion_args(
    started: NativePromotionStarted, *, model_key: str, aspect: str, resolution: str, token: str
) -> list[Any]:
    if (
        not isinstance(resolution, str)
        or resolution not in TARGETS
        or aspect not in {"16:9", "9:16"}
    ):
        raise ConfigurationError(
            detail="Native promotion requires a supported target and inherited video aspect"
        )
    if (
        not isinstance(model_key, str)
        or not 1 <= len(model_key) <= 200
        or not isinstance(token, str)
        or not token
    ):
        raise ConfigurationError(
            detail="Native promotion requires an explicit model key and native token"
        )
    for value in (
        started.project_id,
        started.source_media_id,
        started.source_workflow_id,
        *started.media_ids,
    ):
        _uuid(value)
    if (
        len(started.media_seeds) != 1
        or len(started.media_ids) != 1
        or started.workflow_ids != (started.source_workflow_id,)
        or started.workflow_seeds
        or assigned_id(_uuid(started.media_seeds[0])) != started.media_ids[0]
        or started.media_ids[0]
        in {started.project_id, started.source_media_id, started.source_workflow_id}
    ):
        raise ConfigurationError(detail="Native promotion output identity assignment is invalid")
    row: list[Any] = [None] * 32
    row[0] = [None, started.source_media_id]
    row[2] = {"16:9": 2, "9:16": 1}[aspect]
    # Existing source workflow destination; no new workflow assignment seed.
    row[4] = [None, started.source_workflow_id, None, None, started.media_seeds[0]]
    row[6] = TARGETS[resolution][0]
    row[31] = model_key
    return [
        [row],
        [None, 22, None, None, None, started.project_id, None, None, None, None, [token, 1]],
        [str(uuid4()), 1],
    ]


def parse_promotion_models(payload: Any, *, tier: int, resolution: str) -> list[dict[str, Any]]:
    if (
        not isinstance(resolution, str)
        or not isinstance(resolution, str)
        or resolution not in TARGETS
    ):
        raise ConfigurationError(detail="Native promotion target must be 720p,1080p or4k")
    enum, task = TARGETS[resolution]
    rows = parse_extension_models(payload, tier=tier, required_requirements=(task,))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        resolutions = item["resolution_enums"]
        aspects = item["aspect_enums"]
        if (
            not isinstance(resolutions, list)
            or enum not in resolutions
            or not isinstance(aspects, list)
        ):
            continue
        key = cast(str, item["model_key"])
        if key in seen:
            raise ConfigurationError(detail="Native promotion model inventory has ambiguous keys")
        seen.add(key)
        result.append({**item, "target_resolution": resolution})
    return result


async def list_native_promotion_models(
    client: FlowApiClient, project_id: str, *, resolution: str = "1080p"
) -> list[dict[str, Any]]:
    project = _uuid(project_id)
    if (
        not isinstance(resolution, str)
        or not isinstance(resolution, str)
        or resolution not in TARGETS
    ):
        raise ConfigurationError(detail="Native promotion target must be 720p,1080p or4k")
    page = await client._checkout_page()
    try:
        await page.goto(f"https://flow.google.com/project/{project}", wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
        models = await _read_native(page, "HTrJv", [], project)
        tier = await _read_native(page, "nzlxg", [], project)
        if not isinstance(tier, list) or len(cast(list[Any], tier)) < 4:
            raise ConfigurationError(detail="Native promotion account tier was not observed")
        return parse_promotion_models(models, tier=cast(list[Any], tier)[3], resolution=resolution)
    finally:
        client._checkin_page(page)


@dataclass(frozen=True)
class PromotionSource:
    kind: str
    workflow_id: str
    width: int
    height: int


def promotion_source(snapshot: Any, metadata: Any, *, project: str, media: str) -> PromotionSource:
    rows = parse_media_snapshot(snapshot, project)["media"]
    matches = [row for row in rows if row["media_id"] == media and row["kind"] == "video"]
    if len(matches) != 1:
        raise ValueError("Native promotion requires one active owned video")
    workflow = matches[0]["workflow_id"]
    workflows = [row for row in project_media(snapshot, project) if row["workflow_id"] == workflow]
    if (
        len(workflows) != 1
        or workflows[0]["archived"] is not False
        or workflows[0]["project_id"] != project
        or media not in workflows[0]["batch_media_ids"]
    ):
        raise ValueError("Native promotion source workflow is missing, ambiguous or inactive")
    if not isinstance(metadata, list):
        raise ValueError("Native promotion source metadata is malformed")
    row = cast(list[Any], metadata)
    if (
        len(row) < 8
        or row[:3] != [media, project, workflow]
        or row[6] is not None
        or (len(row) > 10 and row[10] is not None)
    ):
        raise ValueError("Native promotion source identity/type is ambiguous")
    try:
        dimensions = row[7][1]
        width, height = dimensions[:2]
    except (TypeError, IndexError, KeyError, ValueError):
        raise ValueError("Native promotion source dimensions are unavailable") from None
    if any(type(value) is not int or not 0 < value <= 100000 for value in (width, height)):
        raise ValueError("Native promotion source dimensions are invalid")
    return PromotionSource("video", workflow, width, height)


async def read_promotion_source(page: Any, *, project_id: str, media_id: str) -> PromotionSource:
    snapshot = await read_project_payload(page, project_id)
    metadata = await native_rpc(
        page, "as29s", [media_id], "/project/" + project_id, require_single=True
    )
    return promotion_source(snapshot, metadata, project=project_id, media=media_id)


async def upscale_native_video(
    client: FlowApiClient,
    *,
    project_id: str,
    media_id: str,
    resolution: str = "1080p",
    model_key: str | None = None,
    on_started: Callable[[NativePromotionStarted], Awaitable[None]] | None = None,
) -> NativePromotionStarted:
    project, media = _uuid(project_id), _uuid(media_id)
    if (
        not isinstance(resolution, str)
        or resolution not in TARGETS
        or (
            model_key is not None
            and (not isinstance(model_key, str) or not 1 <= len(model_key) <= 200)
        )
    ):
        raise ConfigurationError(detail="Native promotion requires supported target/model controls")
    page = await client._checkout_page()
    try:
        try:
            source = await read_promotion_source(page, project_id=project, media_id=media)
        except ValueError:
            raise ConfigurationError(
                detail="Native promotion source ownership could not be verified"
            ) from None
        if source.kind != "video":
            raise ConfigurationError(detail="Native promotion requires a freshly owned typed video")
        aspect = (
            "9:16"
            if source.width * 16 == source.height * 9
            else "16:9"
            if source.width * 9 == source.height * 16
            else None
        )
        if aspect is None:
            raise ConfigurationError(
                detail="Native promotion source aspect is not supported by the measured builder"
            )
        models = await _read_native(page, "HTrJv", [], project)
        tier = await _read_native(page, "nzlxg", [], project)
        if not isinstance(tier, list) or len(cast(list[Any], tier)) < 4:
            raise ConfigurationError(detail="Native promotion account tier was not observed")
        available = parse_promotion_models(
            models, tier=cast(list[Any], tier)[3], resolution=resolution
        )
        candidates = [
            x
            for x in available
            if {"16:9": 2, "9:16": 1}[aspect] in x["aspect_enums"]
            and (model_key is None or x["model_key"] == model_key)
        ]
        if not candidates:
            raise ConfigurationError(
                detail="No available promotion model matches this source and target"
            )
        selected = min(candidates, key=lambda x: (x["credits"], x["model_key"]))
        started = new_promotion_started(project, media, source.workflow_id, resolution)
        from gflow_cli.api._engine import mint_evaluate_kwargs
        from gflow_cli.api.recaptcha import TokenMinter

        token = await TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs()).mint(
            "VIDEO_GENERATION"
        )
        args = promotion_args(
            started,
            model_key=selected["model_key"],
            aspect=aspect,
            resolution=resolution,
            token=token,
        )
        if on_started:
            await on_started(started)
        try:
            native_captcha_submission()
            result = await page.evaluate(
                _NATIVE_FETCH,
                {"rpc": RPC, "args": args, "source": f"/project/{project}"},
                **page_owned_evaluate_kwargs(),
            )
            refusal = _submit_refusal(
                result["text"], (RPC,), model_key=selected["model_key"], operation="videos/promote"
            )
            if refusal is not None:
                raise refusal
            if result["status"] != 200 or rpc_errors(result["text"]):
                raise NativeVideoUpscaleUnknownError(started)
            expected = {(started.media_ids[0], project, source.workflow_id)}
            acknowledged: set[tuple[str, str, str]] = set()
            for name, envelope in parse_frames(result["text"]):
                if (
                    name != RPC
                    or not isinstance(envelope, list)
                    or len(cast(list[Any], envelope)) < 4
                    or not isinstance(cast(list[Any], envelope)[3], list)
                ):
                    continue
                for raw_record in cast(list[Any], envelope)[3]:
                    record: Any = raw_record
                    if (
                        not isinstance(record, list)
                        or len(cast(list[Any], record)) < 3
                        or cast(tuple[str, str, str], tuple(cast(list[Any], record)[:3]))
                        not in expected
                    ):
                        raise NativeVideoUpscaleUnknownError(started)
                    acknowledged.add(cast(tuple[str, str, str], tuple(cast(list[Any], record)[:3])))
            if acknowledged != expected:
                raise NativeVideoUpscaleUnknownError(started)
            native_captcha_outcome("accepted")
            return started
        except asyncio.CancelledError:
            raise
        except (ContentPolicyError, WafRejectionError, NativeQuotaError):
            native_captcha_outcome("rejected")
            raise
        except NativeVideoUpscaleUnknownError:
            raise
        except Exception:
            raise NativeVideoUpscaleUnknownError(started) from None
    finally:
        client._checkin_page(page)


async def wait_native_promotion(
    client: FlowApiClient, started: NativePromotionStarted, *, timeout_s: float = 600
) -> tuple[Any, ...]:
    try:
        return await wait_native_extension(client, started, timeout_s=timeout_s)
    except NativeExtensionUnknownError:
        raise NativeVideoUpscaleUnknownError(started) from None
