"""Native standalone extension, encoded from the deployed Angular fZytfe builder.

Acceptance is deferred to final live verification. No legacy scene concatenation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from gflow_cli.api._engine import page_owned_evaluate_kwargs
from gflow_cli.api.native_captcha import native_captcha_outcome, native_captcha_submission
from gflow_cli.api.native_catalogs import parse_media_snapshot
from gflow_cli.api.transports.batchexecute import parse_frames, rpc_errors
from gflow_cli.api.transports.migrated_composer import (
    _submit_refusal,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.transports.migrated_resources import read_project_payload
from gflow_cli.errors import (
    ConfigurationError,
    ContentPolicyError,
    NativeExtensionUnknownError,
    NativeQuotaError,
    WafRejectionError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from gflow_cli.api.client import FlowApiClient

RPC = "fZytfe"


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConfigurationError(detail="Native extension requires UUID identifiers") from None


@dataclass(frozen=True)
class NativeExtensionStarted:
    project_id: str
    source_media_id: str
    media_ids: tuple[str, ...]
    workflow_ids: tuple[str, ...]
    media_seeds: tuple[str, ...] = field(default=(), repr=False)
    workflow_seeds: tuple[str, ...] = field(default=(), repr=False)


def assigned_id(seed: str) -> str:
    """Exact deployed pVa UUID derivation from an invocation-owned UUID seed."""
    value = list(sha256(seed[:64].encode()).hexdigest()[:32])
    value[12] = "4"
    value[16] = format((int(value[16], 16) & 3) | 8, "x")
    return str(UUID("".join(value)))


def new_extension_started(project: str, media: str, count: int) -> NativeExtensionStarted:
    if type(count) is not int or count not in range(1, 5):
        raise ConfigurationError(detail="Native extension count must be one through four")
    media_seeds = tuple(str(uuid4()) for _ in range(count))
    workflow_seeds = tuple(str(uuid4()) for _ in range(count))
    return NativeExtensionStarted(
        _uuid(project),
        _uuid(media),
        tuple(assigned_id(seed) for seed in media_seeds),
        tuple(assigned_id(seed) for seed in workflow_seeds),
        media_seeds,
        workflow_seeds,
    )


def extension_args(
    started: NativeExtensionStarted,
    *,
    prompt: str,
    model_key: str,
    aspect: str,
    token: str,
    trim_start_frame: int | None = None,
    trim_end_frame: int | None = None,
) -> list[Any]:
    """Exact K4a/O4a DTO positions; metadata preassigns standalone output IDs."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10000:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ConfigurationError(detail="Native extension requires a nonempty bounded prompt")
    if not isinstance(model_key, str) or not model_key or len(model_key) > 200:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ConfigurationError(detail="Native extension requires an explicit native model key")
    if aspect not in {"16:9", "9:16", "1:1"}:
        raise ConfigurationError(detail="Native extension requires a supported inherited aspect")
    if not isinstance(token, str) or not token:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ConfigurationError(detail="Native extension requires a native CAPTCHA token")
    if len(started.media_ids) not in range(1, 5) or len(started.workflow_ids) != len(
        started.media_ids
    ):
        raise ConfigurationError(detail="Native extension count must be one through four")
    for value in (
        started.project_id,
        started.source_media_id,
        *started.media_ids,
        *started.workflow_ids,
    ):
        _uuid(value)
    if len(set(started.media_ids + started.workflow_ids)) != 2 * len(started.media_ids):
        raise ConfigurationError(detail="Native extension output handles must be distinct")
    for value in (trim_start_frame, trim_end_frame):
        if value is not None and (type(value) is not int or value < 0 or value > 100000):
            raise ConfigurationError(
                detail="Native extension frame trims require nonnegative integers"
            )
    if (
        trim_start_frame is not None
        and trim_end_frame is not None
        and trim_end_frame <= trim_start_frame
    ):
        raise ConfigurationError(detail="Native extension frame range must have positive length")
    video = [None, started.source_media_id, trim_start_frame, trim_end_frame]
    while video[-1] is None:
        video.pop()
    text = [None, None, [[[prompt]]]]
    requests: list[Any] = []
    aspect_enum = {"16:9": 2, "9:16": 1, "1:1": 0}[aspect]
    if tuple(assigned_id(seed) for seed in started.media_seeds) != started.media_ids:
        raise ConfigurationError(detail="Native extension output identity assignment is invalid")
    if tuple(assigned_id(seed) for seed in started.workflow_seeds) != started.workflow_ids:
        raise ConfigurationError(detail="Native extension workflow identity assignment is invalid")
    for media, workflow in zip(started.media_seeds, started.workflow_seeds, strict=True):
        requests.append(
            [video, text, model_key, aspect_enum, None, [None, None, None, None, media, workflow]]
        )
    context = [None, 22, None, None, None, started.project_id, None, None, None, None, [token, 1]]
    return [requests, context, [str(uuid4()), 1]]


_NATIVE_FETCH = """async ({rpc,args,source}) => {
 const w=window.WIZ_global_data;
 const q=new URLSearchParams({rpcids:rpc,'source-path':source,
 bl:w.cfb2h,'f.sid':w.FdrFJe,hl:'en',rt:'c'});
 const body=new URLSearchParams({
 'f.req':JSON.stringify([[[rpc,JSON.stringify(args),null,'generic']]]),at:w.SNlM0e});
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);
 try {const r=await fetch('/_/AiSandboxAngularFrontend/data/batchexecute?'+q,
 {method:'POST',headers:{'content-type':'application/x-www-form-urlencoded;charset=UTF-8'},body,signal:controller.signal});
 const reader=r.body.getReader();let text='',size=0;const decoder=new TextDecoder();
 for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;
 if(size>2097152){await reader.cancel();throw Error('Native response too large');}
 text+=decoder.decode(value,{stream:true});}
 return {status:r.status,text};}finally{clearTimeout(timer);}
}"""


async def extend_native_video(
    client: FlowApiClient,
    *,
    project_id: str,
    media_id: str,
    prompt: str,
    model_key: str | None = None,
    model_family: str | None = None,
    count: int = 1,
    aspect: str | None = None,
    trim_start_frame: int | None = None,
    trim_end_frame: int | None = None,
    on_started: Callable[[NativeExtensionStarted], Awaitable[None]] | None = None,
) -> NativeExtensionStarted:
    """Submit once; checkpoint exact preassigned IDs before the native dispatch."""
    project_id, media_id = _uuid(project_id), _uuid(media_id)
    if model_family is not None:
        from gflow_cli.api.video import VideoModel

        if model_key is not None or model_family not in {
            model.value for model in VideoModel if model != VideoModel.OMNI_FLASH
        }:
            raise ConfigurationError(
                detail="Native extension requires one known Veo family or exact model key"
            )
    if type(count) is not int or count not in range(1, 5):
        raise ConfigurationError(detail="Native extension count must be one through four")
    started = new_extension_started(project_id, media_id, count)
    # Validation before browser checkout, even though aspect will be inherited later.
    extension_args(
        started,
        prompt=prompt,
        model_key=model_key if model_key is not None else "select-native-model",
        aspect=aspect or "16:9",
        token="validation",
        trim_start_frame=trim_start_frame,
        trim_end_frame=trim_end_frame,
    )
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        data = await read_project_payload(page, project_id)
        rows = parse_media_snapshot(data, project_id)["media"]
        source = next(
            (row for row in rows if row["media_id"] == media_id and row["kind"] == "video"), None
        )
        if source is None:
            raise ConfigurationError(detail="Native extension source is not an owned typed video")
        width, height = source.get("width"), source.get("height")
        if width is None and height is None:
            from gflow_cli.api.native_video_upscale import read_owned_video_dimensions

            width, height = await read_owned_video_dimensions(
                page, project_id=project_id, media_id=media_id
            )
        ratios = {(16, 9): "16:9", (9, 16): "9:16", (1, 1): "1:1"}
        inherited = next(
            (
                value
                for (w, h), value in ratios.items()
                if isinstance(width, int) and isinstance(height, int) and width * h == height * w
            ),
            None,
        )
        if inherited is None or (aspect is not None and aspect != inherited):
            raise ConfigurationError(detail="Native extension aspect must match the source video")
        models = await _read_native(page, "HTrJv", [], project_id)
        credits = await _read_native(page, "nzlxg", [], project_id)
        if not isinstance(credits, list) or len(cast("list[Any]", credits)) < 4:
            raise ConfigurationError(detail="Native extension account tier was not observed")
        available = parse_extension_models(models, tier=cast("list[Any]", credits)[3])
        enum = {"16:9": 2, "9:16": 1, "1:1": 0}[inherited]
        candidates = [
            item
            for item in available
            if isinstance(item["aspect_enums"], list) and enum in item["aspect_enums"]
        ]
        if model_key is not None:
            candidates = [item for item in candidates if item["model_key"] == model_key]
        if model_family is not None:
            candidates = [item for item in candidates if item["family"] == model_family]
        if not candidates:
            raise ConfigurationError(
                detail="No tier-available native extension model matches this source"
            )
        selected = min(candidates, key=lambda item: item["credits"])
        model_key = cast("str", selected["model_key"])
        from gflow_cli.api._engine import mint_evaluate_kwargs
        from gflow_cli.api.recaptcha import TokenMinter

        token = await TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs()).mint(
            "VIDEO_GENERATION"
        )
        args = extension_args(
            started,
            prompt=prompt,
            model_key=model_key,
            aspect=inherited,
            token=token,
            trim_start_frame=trim_start_frame,
            trim_end_frame=trim_end_frame,
        )
        if on_started:
            await on_started(started)
        try:
            native_captcha_submission()
            result = await page.evaluate(
                _NATIVE_FETCH,
                {"rpc": RPC, "args": args, "source": f"/project/{project_id}"},
                **page_owned_evaluate_kwargs(),
            )
            refusal = _submit_refusal(
                result["text"], (RPC,), model_key=model_key, operation="videos/extend"
            )
            if refusal is not None:
                raise refusal
            if result["status"] != 200 or rpc_errors(result["text"]):
                raise NativeExtensionUnknownError(started)
            replies = [value for name, value in parse_frames(result["text"]) if name == RPC]
            if not replies:
                raise NativeExtensionUnknownError(started)
            # gy.dg() is field4 of the extension acknowledgement, containing Lx media.
            expected = set(zip(started.media_ids, started.workflow_ids, strict=True))
            acknowledged: set[tuple[str, str]] = set()
            for envelope in replies:
                if not isinstance(envelope, list) or len(cast("list[Any]", envelope)) < 4:
                    continue
                records: Any = cast("list[Any]", envelope)[3]
                if not isinstance(records, list):
                    continue
                for value in cast("list[Any]", records):
                    if not isinstance(value, list) or len(cast("list[Any]", value)) < 3:
                        continue
                    item = cast("list[Any]", value)
                    if item[1] != started.project_id or (item[0], item[2]) not in expected:
                        raise NativeExtensionUnknownError(started)
                    acknowledged.add((item[0], item[2]))
            if acknowledged != expected:
                raise NativeExtensionUnknownError(started)
            native_captcha_outcome("accepted")
            return started
        except asyncio.CancelledError:
            raise
        except NativeExtensionUnknownError:
            raise
        except (WafRejectionError, ContentPolicyError, NativeQuotaError):
            native_captcha_outcome("rejected")
            raise
        except Exception:
            raise NativeExtensionUnknownError(started) from None
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


async def wait_native_extension(
    client: FlowApiClient,
    started: NativeExtensionStarted,
    *,
    timeout_s: float = 600,
) -> tuple[Any, ...]:
    """Read the exact assigned media IDs; never discover outputs by inventory difference."""
    import math

    from gflow_cli.api.transports.batchexecute import GenerationRecord

    if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 900:
        raise ConfigurationError(
            detail="Native extension wait requires a finite 1–900 second timeout"
        )
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    deadline = asyncio.get_running_loop().time() + timeout_s
    completed: dict[str, GenerationRecord] = {}
    try:
        while len(completed) < len(started.media_ids):
            for media, workflow in zip(started.media_ids, started.workflow_ids, strict=True):
                if media in completed:
                    continue
                result = await page.evaluate(
                    _NATIVE_FETCH,
                    {
                        "rpc": "as29s",
                        "args": [media],
                        "source": f"/project/{started.project_id}",
                    },
                    **page_owned_evaluate_kwargs(),
                )
                if result["status"] != 200:
                    raise NativeExtensionUnknownError(started)
                replies = [value for name, value in parse_frames(result["text"]) if name == "as29s"]
                for value in replies:
                    row: Any = value
                    if not isinstance(row, list) or len(cast("list[Any]", row)) < 8:
                        continue
                    # Lx getters: name1/project2/workflow3; current owned as29s confirms.
                    if row[:3] != [media, started.project_id, workflow]:
                        raise NativeExtensionUnknownError(started)
                    # Native media metadata status9 and generated video URL9.
                    from gflow_cli.api.transports.batchexecute import (
                        _at,  # pyright: ignore[reportPrivateUsage]
                    )

                    status: Any = _at(cast("list[Any]", row), 5, 8, 0)
                    if status in {4, 5, 7}:
                        raise NativeExtensionUnknownError(started)
                    url: Any = _at(cast("list[Any]", row), 7, 0, 8)
                    if status == 3 and isinstance(url, str) and url.startswith("https://"):
                        completed[media] = GenerationRecord(
                            workflow,
                            started.project_id,
                            media,
                            status,
                            video_url=url,
                        )
            remaining = deadline - asyncio.get_running_loop().time()
            if len(completed) < len(started.media_ids):
                if remaining <= 0:
                    raise NativeExtensionUnknownError(started)
                await asyncio.sleep(min(5, remaining))
        return tuple(completed[media] for media in started.media_ids)
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]


def parse_extension_models(
    payload: Any, *, tier: int, required_requirements: tuple[int, ...] = (1, 14)
) -> list[dict[str, Any]]:
    """Decode HTrJv's current video families; retain only tier-available EXTEND usages."""
    if type(tier) is not int or tier not in {1, 2, 3}:
        raise ConfigurationError(detail="Native model discovery requires an observed account tier")
    from gflow_cli.api.transports.batchexecute import _at  # pyright: ignore[reportPrivateUsage]

    families: Any = _at(payload, 0, 4)
    if not isinstance(families, list):
        raise ConfigurationError(detail="Native model listing has no video families")
    result: list[dict[str, Any]] = []
    for raw in cast("list[Any]", families):
        family: Any = raw
        if _at(family, 5) is True:
            continue
        usages: Any = _at(family, 1)
        if not isinstance(usages, list):
            continue
        for raw_usage in cast("list[Any]", usages):
            usage: Any = raw_usage
            if _at(usage, 24) is True:
                continue
            options: Any = _at(usage, 7, 0)
            matches = False
            if isinstance(options, list):
                for option in cast("list[Any]", options):
                    requirements: Any = _at(option, 0)
                    if isinstance(requirements, list) and all(
                        item in requirements for item in required_requirements
                    ):
                        matches = True
            if not matches:
                continue
            costs: Any = _at(usage, 4)
            available: Any = None
            if isinstance(costs, list):
                for raw_entry in cast("list[Any]", costs):
                    entry: Any = raw_entry
                    if _at(entry, 0) == tier:
                        available = _at(entry, 1)
                        break
            if _at(available, 1) is not None:
                continue
            cost: Any = _at(available, 0, 1)
            key: Any = _at(usage, 0)
            if not isinstance(key, str) or type(cost) is not int or cost < 0:
                continue
            aspects: Any = _at(usage, 12, 0)
            result.append(
                {
                    "model_key": key,
                    "family": _at(family, 3),
                    "display_name": _at(family, 0),
                    "credits": cost,
                    "duration": _at(usage, 16) or 8,
                    "aspect_enums": aspects,
                    "max_images": _at(usage, 21, 2),
                    "max_audio": _at(usage, 21, 0),
                    "max_characters": _at(usage, 21, 1),
                    "resolution_enums": _at(usage, 23, 0),
                    "duration_flexible": _at(usage, 22) is True,
                }
            )
    return result


async def _read_native(page: Any, rpc: str, args: list[Any], project: str) -> Any:
    result = await page.evaluate(
        _NATIVE_FETCH,
        {"rpc": rpc, "args": args, "source": f"/project/{project}"},
        **page_owned_evaluate_kwargs(),
    )
    if result["status"] != 200 or rpc_errors(result["text"]):
        raise ConfigurationError(detail="Native extension model metadata could not be read")
    for name, data in parse_frames(result["text"]):
        if name == rpc:
            return data
    raise ConfigurationError(detail="Native extension model metadata was not acknowledged")


async def list_native_extension_models(
    client: FlowApiClient, project_id: str
) -> list[dict[str, Any]]:
    project = _uuid(project_id)
    page = await client._checkout_page()  # pyright: ignore[reportPrivateUsage]
    try:
        await page.goto(f"https://flow.google.com/project/{project}", wait_until="domcontentloaded")
        await page.wait_for_function("() => Boolean(window.WIZ_global_data?.SNlM0e)", timeout=10000)
        models = await _read_native(page, "HTrJv", [], project)
        credits = await _read_native(page, "nzlxg", [], project)
        if not isinstance(credits, list) or len(cast("list[Any]", credits)) < 4:
            raise ConfigurationError(detail="Native account tier was not observed")
        return parse_extension_models(models, tier=cast("list[Any]", credits)[3])
    finally:
        client._checkin_page(page)  # pyright: ignore[reportPrivateUsage]
